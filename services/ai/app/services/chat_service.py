"""Chat service — hybrid RAG pipeline: QVAC dense + BM25 sparse + reranker + parent context."""
import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List

import httpx

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    """Remove Markdown syntax and PDF artefacts from a text block before passing it to the LLM."""
    # LaTeX source metadata lines ("Ammous c01.tex V1 - 03/05/2018 1:08pm Page 10")
    text = re.sub(r'^[A-Za-z]+\s+\w+\.tex\s+V\d+[^\n]*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_\n]+)_{1,3}', r'\1', text)
    text = re.sub(r'^\|[\s|:-]+\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _clean_answer(text: str) -> str:
    """Post-process raw LLM output: strip artefacts, trailing delimiters, markdown."""
    text = text.strip()
    text = re.sub(r'(===+|---+)\s*$', '', text).strip()
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text if text else "Risposta non disponibile."


_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
# RAG_RETRIEVE_K: total candidates fetched from dense + sparse pool.
# RAG_TOP_K: chunks handed to the LLM after reranking (context window budget).
_TOP_K_RETRIEVE = int(os.getenv("RAG_RETRIEVE_K", "20"))
_TOP_K_GENERATE = int(os.getenv("RAG_TOP_K", "5"))
# RAG_MAX_CONTEXT_TOKENS: rough token budget (words × 1.3) for context blocks.
_MAX_CONTEXT_TOKENS = int(os.getenv("RAG_MAX_CONTEXT_TOKENS", "6000"))

_client = httpx.AsyncClient(base_url=_QVAC_SERVICE_URL, timeout=60.0)

# ---------------------------------------------------------------------------
# ChromaDB fallback (lazy singleton — initialized on first use)
# ---------------------------------------------------------------------------

_chroma_db: dict = {}  # keys: "collection", "model"


def _chroma_retrieve(query: str, course_id: str, top_k: int) -> list[EvidenceChunk]:
    """Dense retrieval from ChromaDB using all-MiniLM-L6-v2 when QVAC is unavailable."""
    global _chroma_db
    try:
        import chromadb  # noqa: PLC0415
        from chromadb.config import Settings as ChromaSettings  # noqa: PLC0415
        from fastembed import TextEmbedding  # noqa: PLC0415

        if not _chroma_db:
            chroma_path = os.getenv("CHROMA_DB_PATH", "")
            if not chroma_path:
                logger.warning("ChromaDB fallback skipped: CHROMA_DB_PATH not set")
                return []
            client = chromadb.PersistentClient(
                path=chroma_path,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            cname = os.getenv("CHROMA_COLLECTION_NAME", "bitpolito_course")
            try:
                _chroma_db["collection"] = client.get_collection(cname)
            except Exception:
                logger.warning("ChromaDB collection '%s' not found — fallback unavailable", cname)
                return []
            _chroma_db["model"] = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

        collection = _chroma_db["collection"]
        model = _chroma_db["model"]

        n_results = min(top_k, collection.count())
        if n_results == 0:
            return []

        embedding = list(model.embed([query]))[0].tolist()
        results = collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where={"course_id": course_id},
            include=["documents", "metadatas", "distances"],
        )

        chunks: list[EvidenceChunk] = []
        for cid, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = max(0.0, 1.0 - float(dist))
            chunks.append(EvidenceChunk(
                chunk_id=cid,
                text=doc,
                score=round(score, 6),
                anchor=CitationAnchor(
                    doc_id=meta.get("doc_id", ""),
                    doc_name=meta.get("label", meta.get("filename", "")),
                    section=meta.get("section") or None,
                    page=int(meta["page"]) if meta.get("page") else None,
                    slide=int(meta["slide"]) if meta.get("slide") else None,
                    chunk_id=cid,
                    chunk_type=meta.get("chunk_type", "paragraph"),
                ),
            ))

        logger.info("ChromaDB fallback: %d chunks for course '%s'", len(chunks), course_id)
        return chunks

    except Exception as exc:
        logger.warning("ChromaDB fallback retrieval failed: %s", exc)
        _chroma_db = {}  # reset singleton so next call re-initialises
        return []


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    snippet: str
    score: float
    label: str = ""
    page: int = 0
    slide: int = 0
    section: str = ""
    doc_id: str = ""


@dataclass
class ChatResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    retrieval_used: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _qvac_dict_to_chunk(d: dict) -> EvidenceChunk:
    """Convert a QVAC /retrieve response dict to an EvidenceChunk."""
    return EvidenceChunk(
        chunk_id=d.get("chunk_id", ""),
        text=d.get("content", "") or d.get("text", ""),
        score=float(d.get("score", 0.0)),
        anchor=CitationAnchor(
            doc_id=d.get("doc_id", ""),
            doc_name=d.get("label", ""),
            section=d.get("section") or None,
            page=int(d["page"]) if d.get("page") else None,
            slide=int(d["slide"]) if d.get("slide") else None,
            chunk_id=d.get("chunk_id", ""),
            chunk_type="paragraph",
        ),
    )


async def _retrieve_and_rank(
    question: str,
    course_id: str,
    retrieval_query: str,
) -> tuple[list[dict], list[Citation]]:
    """Dense + sparse retrieval, normalized fusion, rerank, MMR, parent expansion.

    Primary dense source: QVAC (GTE-Large embeddings).
    Fallback dense source: ChromaDB (all-MiniLM-L6-v2) when QVAC /retrieve is unavailable.
    Raises httpx.HTTPError only when BOTH sources fail.
    """
    from app.services import hybrid_search, reranker, parent_expansion  # noqa: PLC0415
    from app.rag.compressor import compress_passages  # noqa: PLC0415

    # ── Dense retrieval (QVAC primary → ChromaDB fallback) ───────────────────
    dense_chunks: list[EvidenceChunk] = []
    try:
        resp = await _client.post(
            "/retrieve",
            json={"question": retrieval_query, "workspace": course_id, "topK": _TOP_K_RETRIEVE},
        )
        resp.raise_for_status()
        dense_chunks = [_qvac_dict_to_chunk(d) for d in resp.json().get("chunks", []) if d.get("chunk_id")]
    except httpx.HTTPError as exc:
        logger.info("QVAC /retrieve unavailable (%s) — trying ChromaDB fallback", exc)
        dense_chunks = await asyncio.get_event_loop().run_in_executor(
            None, _chroma_retrieve, retrieval_query, course_id, _TOP_K_RETRIEVE
        )
        if not dense_chunks:
            raise  # re-raise so caller shows "service unavailable" message

    # ── Sparse retrieval (BM25) + normalized hybrid fusion ───────────────────
    bm25_hits = hybrid_search.bm25_search(question, course_id, top_k=_TOP_K_RETRIEVE)
    if bm25_hits:
        index_data = hybrid_search.load_bm25_index(course_id)
        corpus = index_data[2] if index_data else {}
        merged = hybrid_search.normalized_hybrid_fuse(
            dense_chunks, bm25_hits, corpus, top_k=_TOP_K_RETRIEVE
        )
    else:
        logger.debug("BM25 index absent for course '%s' — dense-only retrieval", course_id)
        merged = dense_chunks[:_TOP_K_RETRIEVE]

    # ── Rerank + MMR diversity + parent context expansion ────────────────────
    reranked_all = reranker.rerank(question, merged)
    reranked = reranker.mmr_select(reranked_all, _TOP_K_GENERATE)
    context_chunks = parent_expansion.expand_to_parents(reranked)

    # ── Context compression (opt-in via RAG_COMPRESS_CONTEXT=true) ───────────
    # Runs in executor to avoid blocking the event loop (QVAC /generate calls).
    texts_raw = [_strip_markdown(c.text) for c in context_chunks]
    compressed_texts: list[str] = await asyncio.get_event_loop().run_in_executor(
        None, compress_passages, question, texts_raw
    )

    # ── Token budget assembly ─────────────────────────────────────────────────
    context_blocks: list[dict] = []
    total_est_tokens = 0
    for c, clean_text in zip(context_chunks, compressed_texts):
        est_tokens = int(len(clean_text.split()) * 1.3)
        if total_est_tokens + est_tokens > _MAX_CONTEXT_TOKENS:
            break
        total_est_tokens += est_tokens
        loc = (
            f"p.{c.anchor.page}" if c.anchor.page
            else (f"slide {c.anchor.slide}" if c.anchor.slide else "")
        )
        label = f"{c.anchor.doc_name} · {loc}" if loc else c.anchor.doc_name
        context_blocks.append({"label": label, "text": clean_text})

    citations = [
        Citation(
            snippet=c.text[:200],
            score=c.score,
            label=c.anchor.doc_name,
            page=c.anchor.page or 0,
            slide=c.anchor.slide or 0,
            section=c.anchor.section or "",
            doc_id=c.anchor.doc_id,
        )
        for c in reranked
    ]
    return context_blocks, citations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def answer(
    question: str,
    course_id: str,
    history: list[dict] | None = None,
) -> ChatResult:
    """Hybrid RAG answer: dense (QVAC) + sparse (BM25) → RRF → rerank → parent context → LLM."""
    from app.rag.query_rewriter import expand_query  # noqa: PLC0415
    from app.services.cache_service import get_cached, set_cached  # noqa: PLC0415

    # Semantic cache — skip pipeline on near-duplicate query.
    cached = get_cached(question, course_id)
    if cached is not None:
        return ChatResult(
            answer=cached["answer"],
            citations=[Citation(**c) for c in cached.get("citations", [])],
            retrieval_used=cached.get("retrieval_used", True),
        )

    retrieval_query = await expand_query(question)

    try:
        context_blocks, citations = await _retrieve_and_rank(question, course_id, retrieval_query)
    except httpx.HTTPError as exc:
        logger.warning("QVAC /retrieve unavailable (%s)", exc)
        return ChatResult(
            answer="Il servizio di ricerca non è disponibile. Riprova tra qualche istante.",
            citations=[],
            retrieval_used=False,
        )

    if history:
        history_lines = [
            f"{'Student' if m['role'] == 'user' else 'Tutor'}: {m['content'][:500]}"
            for m in history[-4:]
        ]
        context_blocks.insert(0, {
            "label": "Cronologia conversazione",
            "text": "\n".join(history_lines),
        })

    answer_text = ""
    try:
        gen_resp = await _client.post(
            "/generate",
            json={"question": question, "context": context_blocks},
        )
        gen_resp.raise_for_status()
        answer_text = _clean_answer(gen_resp.json().get("answer", ""))
    except httpx.HTTPError as exc:
        logger.warning("QVAC /generate failed (%s) — returning truncated context snippet", exc)
        if context_blocks:
            raw = context_blocks[0]["text"]
            snippet = raw[:600].rstrip() + ("…" if len(raw) > 600 else "")
            answer_text = f"Generazione LLM non disponibile. Passaggio più rilevante:\n\n{snippet}"
        else:
            answer_text = "Risposta non disponibile."

    citations_json = [
        {"snippet": c.snippet, "score": c.score, "label": c.label,
         "page": c.page, "slide": c.slide, "section": c.section, "doc_id": c.doc_id}
        for c in citations
    ]
    set_cached(question, course_id, {
        "answer": answer_text,
        "citations": citations_json,
        "retrieval_used": bool(citations),
    })

    return ChatResult(answer=answer_text, citations=citations, retrieval_used=bool(citations))


async def stream_answer(
    question: str,
    course_id: str,
    history: list[dict] | None = None,
):
    """Stream tokens from QVAC /stream using the same retrieval pipeline as answer().

    Yields raw token strings.  Ends with a special "\x00CITATIONS\x00<json>"
    sentinel so the client can render citations after streaming completes.
    Falls back to buffered /generate when QVAC /stream is unavailable.
    Serves cached answer as a single burst when a near-duplicate query hits the cache.
    """
    import json as _json  # noqa: PLC0415
    from app.rag.query_rewriter import expand_query  # noqa: PLC0415
    from app.services.cache_service import get_cached, set_cached  # noqa: PLC0415

    cached = get_cached(question, course_id)
    if cached is not None:
        yield cached["answer"]
        yield "\x00CITATIONS\x00" + _json.dumps(cached.get("citations", []))
        return

    retrieval_query = await expand_query(question)

    try:
        context_blocks, citations = await _retrieve_and_rank(question, course_id, retrieval_query)
    except httpx.HTTPError as exc:
        logger.warning("QVAC /retrieve unavailable (%s)", exc)
        yield "Il servizio di ricerca non è disponibile. Riprova tra qualche istante."
        return

    if history:
        history_lines = [
            f"{'Student' if m['role'] == 'user' else 'Tutor'}: {m['content'][:500]}"
            for m in history[-4:]
        ]
        context_blocks.insert(0, {
            "label": "Cronologia conversazione",
            "text": "\n".join(history_lines),
        })

    citations_json = [
        {"snippet": c.snippet, "score": c.score, "label": c.label,
         "page": c.page, "slide": c.slide, "section": c.section, "doc_id": c.doc_id}
        for c in citations
    ]

    accumulated: list[str] = []
    stream_failed = False

    try:
        async with _client.stream(
            "POST", "/stream",
            json={"question": question, "context": context_blocks},
            timeout=120.0,
        ) as stream_resp:
            stream_resp.raise_for_status()
            async for line in stream_resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    token = _json.loads(payload)
                except Exception:
                    token = payload
                # QVAC returns "[ERROR] ..." as a regular token when the LLM is busy.
                # Treat any error token as a stream failure and fall back to /generate.
                if isinstance(token, str) and token.startswith("[ERROR]"):
                    logger.warning("QVAC /stream error token: %s", token)
                    stream_failed = True
                    break
                yield token
                accumulated.append(token)
    except httpx.HTTPError as exc:
        logger.warning("QVAC /stream failed (%s) — falling back to buffered generate", exc)
        stream_failed = True

    # Fall back to buffered /generate when streaming errored or returned nothing.
    if stream_failed or not accumulated:
        try:
            gen_resp = await _client.post(
                "/generate",
                json={"question": question, "context": context_blocks},
            )
            gen_resp.raise_for_status()
            token = _clean_answer(gen_resp.json().get("answer", ""))
            if not token:
                token = "Risposta non disponibile."
            yield token
            accumulated.append(token)
        except httpx.HTTPError as exc2:
            logger.warning("QVAC /generate also failed (%s)", exc2)
            if context_blocks:
                raw = context_blocks[0]["text"]
                snippet = raw[:600].rstrip() + ("…" if len(raw) > 600 else "")
                token = f"Generazione LLM non disponibile. Passaggio più rilevante:\n\n{snippet}"
            else:
                token = "Risposta non disponibile."
            yield token
            accumulated.append(token)

    full_answer = "".join(accumulated)
    if full_answer:
        set_cached(question, course_id, {
            "answer": full_answer,
            "citations": citations_json,
            "retrieval_used": bool(citations),
        })

    yield "\x00CITATIONS\x00" + _json.dumps(citations_json)
