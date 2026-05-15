"""Chat service — hybrid RAG pipeline: QVAC dense + BM25 sparse + reranker + parent context."""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List

import httpx

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    """Remove Markdown syntax from a text block before passing it to the LLM."""
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


_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "")
# RAG_RETRIEVE_K: total candidates fetched from dense + sparse pool.
# RAG_TOP_K: chunks handed to the LLM after reranking (context window budget).
_TOP_K_RETRIEVE = int(os.getenv("RAG_RETRIEVE_K", "20"))
_TOP_K_GENERATE = int(os.getenv("RAG_TOP_K", "5"))
# RAG_MAX_CONTEXT_TOKENS: rough token budget (words × 1.3) for context blocks.
_MAX_CONTEXT_TOKENS = int(os.getenv("RAG_MAX_CONTEXT_TOKENS", "6000"))

_client = httpx.AsyncClient(base_url=_QVAC_SERVICE_URL, timeout=60.0)


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


# ---------------------------------------------------------------------------
# ChromaDB fallback
# ---------------------------------------------------------------------------

def _chroma_chat_result(question: str, course_id: str) -> ChatResult:
    """Query ChromaDB and return a ChatResult with raw snippets as answer."""
    from app.services.chroma_retrieval import query_chroma  # noqa: PLC0415
    sources = query_chroma(question, course_id, top_k=_TOP_K_GENERATE)
    citations = [
        Citation(
            snippet=s["snippet"],
            score=s["score"],
            label=s["label"],
            page=s["page"],
            slide=s["slide"],
            section=s["section"],
            doc_id=s["doc_id"],
        )
        for s in sources
    ]
    answer_text = (
        f"Found {len(sources)} relevant passage{'s' if len(sources) != 1 else ''} (LLM generation unavailable)."
        if sources
        else "No relevant content found."
    )
    return ChatResult(answer=answer_text, citations=citations, retrieval_used=bool(citations))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def answer(
    question: str,
    course_id: str,
    history: list[dict] | None = None,
) -> ChatResult:
    """Hybrid RAG answer: dense (QVAC) + sparse (BM25) → RRF → rerank → parent context → LLM.

    Flow:
      0. Semantic cache lookup (skip full pipeline on cache hit)
      1. /retrieve  — top-20 dense chunks from QVAC
      2. BM25 sparse search on local index
      3. RRF fusion → unified top-20
      4. Cross-encoder rerank (FlashRank) → top-5
      5. Parent context expansion (child text → 1200-word parent block)
      6. /generate  — LLM answer from parent contexts
    Falls back to ChromaDB when QVAC is unavailable.
    """
    from app.services import hybrid_search, reranker, parent_expansion  # noqa: PLC0415
    from app.rag.query_rewriter import expand_query  # noqa: PLC0415
    from app.services.cache_service import get_cached, set_cached  # noqa: PLC0415

    # 0. Semantic cache — return cached answer for near-duplicate queries.
    cached = get_cached(question, course_id)
    if cached is not None:
        return ChatResult(
            answer=cached["answer"],
            citations=[Citation(**c) for c in cached.get("citations", [])],
            retrieval_used=cached.get("retrieval_used", True),
        )

    # 0b. Query expansion (HyDE / rewrite) — original question kept for generation.
    retrieval_query = await expand_query(question)

    # 1. Dense retrieval
    try:
        resp = await _client.post(
            "/retrieve",
            json={"question": retrieval_query, "workspace": course_id, "topK": _TOP_K_RETRIEVE},
        )
        resp.raise_for_status()
        dense_dicts: list[dict] = resp.json().get("chunks", [])
    except httpx.HTTPError as exc:
        logger.warning("QVAC /retrieve unavailable (%s) — trying ChromaDB fallback", exc)
        return _chroma_chat_result(question, course_id)

    if not dense_dicts:
        logger.info("QVAC returned 0 chunks for course '%s', trying ChromaDB fallback", course_id)
        fallback = _chroma_chat_result(question, course_id)
        if fallback.citations:
            return fallback

    # 2. Convert QVAC dicts → EvidenceChunk for unified processing
    dense_chunks = [_qvac_dict_to_chunk(d) for d in dense_dicts if d.get("chunk_id")]

    # 3. BM25 sparse retrieval
    bm25_hits = hybrid_search.bm25_search(question, course_id, top_k=_TOP_K_RETRIEVE)

    # 4. RRF fusion — falls back to dense-only when BM25 index is absent
    if bm25_hits:
        index_data = hybrid_search.load_bm25_index(course_id)
        corpus = index_data[2] if index_data else {}
        merged = hybrid_search.rrf_fuse(dense_chunks, bm25_hits, corpus, top_k=_TOP_K_RETRIEVE)
    else:
        logger.debug("BM25 index absent for course '%s' — dense-only retrieval", course_id)
        merged = dense_chunks[:_TOP_K_RETRIEVE]

    # 5. Rerank with FlashRank cross-encoder → MMR diversity selection → top _TOP_K_GENERATE
    reranked_all = reranker.rerank(question, merged)
    reranked = reranker.mmr_select(reranked_all, _TOP_K_GENERATE)

    # 6. Expand child chunks → parent context (richer LLM context window)
    context_chunks = parent_expansion.expand_to_parents(reranked)

    # 7. Build context blocks: strip Markdown, deduplicate by parent_id, enforce token budget
    context_blocks = []
    total_est_tokens = 0
    for c in context_chunks:
        clean_text = _strip_markdown(c.text)
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

    # 7b. Prepend conversation history as first context block (Q1)
    if history:
        history_lines = [
            f"{'Student' if m['role'] == 'user' else 'Tutor'}: {m['content'][:500]}"
            for m in history[-4:]
        ]
        context_blocks.insert(0, {
            "label": "Cronologia conversazione",
            "text": "\n".join(history_lines),
        })

    # 8. LLM generation
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

    # 9. Citations from child chunks (preserves page/slide precision)
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

    result = ChatResult(answer=answer_text, citations=citations, retrieval_used=bool(reranked))

    # Store in semantic cache for future near-duplicate queries.
    set_cached(question, course_id, {
        "answer": answer_text,
        "citations": [
            {"snippet": c.snippet, "score": c.score, "label": c.label,
             "page": c.page, "slide": c.slide, "section": c.section, "doc_id": c.doc_id}
            for c in citations
        ],
        "retrieval_used": bool(reranked),
    })

    return result


async def stream_answer(
    question: str,
    course_id: str,
    history: list[dict] | None = None,
):
    """Async generator: same retrieval pipeline as answer(), but streams tokens from QVAC /stream.

    Yields strings — each is a raw token from the LLM.  Terminates with a
    special JSON sentinel object {"citations": [...], "retrieval_used": bool}
    so the client can render citations after streaming completes.
    Falls back to answer() when QVAC /stream is unavailable.
    """
    import json as _json  # noqa: PLC0415
    from app.services import hybrid_search, reranker, parent_expansion  # noqa: PLC0415
    from app.rag.query_rewriter import expand_query  # noqa: PLC0415

    retrieval_query = await expand_query(question)

    try:
        resp = await _client.post(
            "/retrieve",
            json={"question": retrieval_query, "workspace": course_id, "topK": _TOP_K_RETRIEVE},
        )
        resp.raise_for_status()
        dense_dicts: list[dict] = resp.json().get("chunks", [])
    except httpx.HTTPError:
        fallback = _chroma_chat_result(question, course_id)
        yield fallback.answer
        return

    dense_chunks = [_qvac_dict_to_chunk(d) for d in dense_dicts if d.get("chunk_id")]
    bm25_hits = hybrid_search.bm25_search(question, course_id, top_k=_TOP_K_RETRIEVE)

    if bm25_hits:
        index_data = hybrid_search.load_bm25_index(course_id)
        corpus = index_data[2] if index_data else {}
        merged = hybrid_search.rrf_fuse(dense_chunks, bm25_hits, corpus, top_k=_TOP_K_RETRIEVE)
    else:
        merged = dense_chunks[:_TOP_K_RETRIEVE]

    reranked_all = reranker.rerank(question, merged)
    reranked = reranker.mmr_select(reranked_all, _TOP_K_GENERATE)
    context_chunks = parent_expansion.expand_to_parents(reranked)

    context_blocks = []
    total_est_tokens = 0
    for c in context_chunks:
        clean_text = _strip_markdown(c.text)
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

    if history:
        history_lines = [
            f"{'Student' if m['role'] == 'user' else 'Tutor'}: {m['content'][:500]}"
            for m in history[-4:]
        ]
        context_blocks.insert(0, {"label": "Cronologia conversazione", "text": "\n".join(history_lines)})

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
                    yield token
                except Exception:
                    yield payload
    except httpx.HTTPError as exc:
        logger.warning("QVAC /stream failed (%s) — falling back to buffered generate", exc)
        try:
            gen_resp = await _client.post(
                "/generate",
                json={"question": question, "context": context_blocks},
            )
            gen_resp.raise_for_status()
            yield _clean_answer(gen_resp.json().get("answer", "Risposta non disponibile."))
        except httpx.HTTPError:
            yield "Risposta non disponibile."

    # Emit citations as the final SSE event so the client can display them.
    yield "\x00CITATIONS\x00" + _json.dumps([
        {"snippet": c.snippet, "score": c.score, "label": c.label,
         "page": c.page, "slide": c.slide, "section": c.section, "doc_id": c.doc_id}
        for c in citations
    ])
