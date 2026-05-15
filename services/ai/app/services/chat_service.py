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


_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "")
# RAG_RETRIEVE_K: total candidates fetched from dense + sparse pool.
# RAG_TOP_K: chunks handed to the LLM after reranking (context window budget).
_TOP_K_RETRIEVE = int(os.getenv("RAG_RETRIEVE_K", "20"))
_TOP_K_GENERATE = int(os.getenv("RAG_TOP_K", "5"))

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

async def answer(question: str, course_id: str) -> ChatResult:
    """Hybrid RAG answer: dense (QVAC) + sparse (BM25) → RRF → rerank → parent context → LLM.

    Flow:
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

    # 0. Query expansion (HyDE / rewrite) — original question kept for generation.
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

    # 5. Rerank with FlashRank cross-encoder → keep top _TOP_K_GENERATE
    reranked_all = reranker.rerank(question, merged)
    reranked = reranked_all[:_TOP_K_GENERATE]

    # 6. Expand child chunks → parent context (richer LLM context window)
    context_chunks = parent_expansion.expand_to_parents(reranked)

    # 7. Build context blocks for LLM generation (strip Markdown to avoid symbol pollution)
    context_blocks = [
        {"label": c.anchor.doc_name, "text": _strip_markdown(c.text)}
        for c in context_chunks
    ]

    # 8. LLM generation
    answer_text = ""
    try:
        gen_resp = await _client.post(
            "/generate",
            json={"question": question, "context": context_blocks},
        )
        gen_resp.raise_for_status()
        answer_text = gen_resp.json().get("answer", "")
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

    return ChatResult(answer=answer_text, citations=citations, retrieval_used=bool(reranked))
