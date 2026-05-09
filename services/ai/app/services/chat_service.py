"""Chat service — hybrid search (QVAC dense + BM25 sparse) with parent-child context."""
import asyncio
import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import httpx

logger = logging.getLogger(__name__)

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "")
# RAG_RETRIEVE_K: total chunks fetched for hybrid search (dense + sparse pool).
# RAG_TOP_K: chunks passed to the LLM after reranking (context window budget).
_TOP_K_RETRIEVE = int(os.getenv("RAG_RETRIEVE_K", "20"))
_TOP_K_GENERATE = int(os.getenv("RAG_TOP_K", "5"))

# Directory where BM25 corpus.json and bm25.pkl are stored (same as QVAC_INGEST_DIR).
_QVAC_INGEST_DIR = Path(os.getenv("QVAC_INGEST_DIR", ""))

_client = httpx.AsyncClient(base_url=_QVAC_SERVICE_URL, timeout=60.0)

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from flashrank import Ranker
            _reranker = Ranker(model_name="ms-marco-MiniLM-L-6-v2", cache_dir="/tmp/flashrank")
            logger.info("FlashRank reranker loaded (ms-marco-MiniLM-L-6-v2)")
        except Exception as exc:
            logger.warning("FlashRank unavailable — skipping reranking: %s", exc)
    return _reranker


def _rerank_sources(question: str, sources: list) -> list:
    """Rerank with FlashRank cross-encoder; returns top _TOP_K_GENERATE results."""
    if len(sources) <= 1:
        return sources[:_TOP_K_GENERATE]
    reranker = _get_reranker()
    if reranker is None:
        return sources[:_TOP_K_GENERATE]
    try:
        from flashrank import RerankRequest
        passages = [
            {"id": i, "text": s.get("content") or s.get("snippet", "")}
            for i, s in enumerate(sources)
        ]
        reranked = reranker.rerank(RerankRequest(query=question, passages=passages))
        top_ids = [r["id"] for r in reranked[:_TOP_K_GENERATE]]
        return [sources[i] for i in top_ids]
    except Exception as exc:
        logger.warning("FlashRank reranking failed, falling back to dense order: %s", exc)
        return sources[:_TOP_K_GENERATE]


# ---------------------------------------------------------------------------
# BM25 helpers
# ---------------------------------------------------------------------------

def _bm25_search(question: str, course_id: str, top_k: int = 20) -> list[dict]:
    """Query the BM25 sparse index for the course; returns [{chunk_id, score}]."""
    if not _QVAC_INGEST_DIR:
        return []
    bm25_path = _QVAC_INGEST_DIR / f"{course_id}_bm25.pkl"
    if not bm25_path.exists():
        return []
    try:
        with bm25_path.open("rb") as f:
            data = pickle.load(f)
        bm25 = data["bm25"]
        ids = data["ids"]
        tokens = question.lower().split()
        scores = bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [{"chunk_id": ids[i], "score": float(scores[i])} for i in ranked if scores[i] > 0]
    except Exception as exc:
        logger.warning("BM25 search failed for course '%s': %s", course_id, exc)
        return []


def _rrf_merge(
    dense_chunks: list[dict],
    bm25_results: list[dict],
    top_n: int = 20,
    k: int = 60,
) -> list[str]:
    """Reciprocal Rank Fusion over dense (QVAC) and sparse (BM25) results.

    Dense chunks are keyed by their original chunk_id field.
    Returns an ordered list of chunk_ids.
    """
    rrf: dict[str, float] = {}

    for rank, chunk in enumerate(dense_chunks):
        cid = chunk.get("chunk_id", "")
        if cid:
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (rank + k)

    for rank, item in enumerate(bm25_results):
        cid = item["chunk_id"]
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (rank + k)

    return sorted(rrf.keys(), key=lambda x: rrf[x], reverse=True)[:top_n]


def _load_corpus(course_id: str) -> dict:
    """Load the BM25 corpus JSON for the course (lazy, per-request)."""
    if not _QVAC_INGEST_DIR:
        return {}
    corpus_path = _QVAC_INGEST_DIR / f"{course_id}_corpus.json"
    if not corpus_path.exists():
        return {}
    try:
        with corpus_path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_merged(
    merged_ids: list[str],
    dense_registry: dict[str, dict],
    course_id: str,
) -> list[dict]:
    """Map RRF-merged chunk_ids to full chunk info.

    Uses QVAC dense results first; falls back to corpus.json for BM25-only chunks.
    """
    bm25_only = [cid for cid in merged_ids if cid not in dense_registry]
    corpus = _load_corpus(course_id) if bm25_only else {}

    result = []
    for cid in merged_ids:
        if cid in dense_registry:
            result.append(dense_registry[cid])
        elif cid in corpus:
            entry = corpus[cid]
            result.append({
                "chunk_id": cid,
                "content": entry.get("text", ""),
                "score": 0.0,
                "label": entry.get("label", ""),
                "page": entry.get("page", 0),
                "slide": 0,
                "section": entry.get("section", ""),
                "doc_id": entry.get("doc_id", ""),
                "parent_id": entry.get("parent_id", ""),
            })
    return result


# ---------------------------------------------------------------------------
# Parent lookup
# ---------------------------------------------------------------------------

def _load_parents_from_db(parent_ids: list[str]) -> dict[str, dict]:
    """Sync DB query: returns {parent_id: {text, label}}."""
    if not parent_ids:
        return {}
    try:
        from app.db.session import get_db_context   # noqa: PLC0415
        from app.db.models import ChunkParent        # noqa: PLC0415
        with get_db_context() as db:
            rows = db.query(ChunkParent).filter(ChunkParent.id.in_(parent_ids)).all()
        return {r.id: {"text": r.text, "label": r.citation_label} for r in rows}
    except Exception as exc:
        logger.warning("Parent DB lookup failed: %s", exc)
        return {}


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
        "\n\n---\n\n".join(s["snippet"] for s in sources)
        if sources
        else "No relevant content found."
    )
    return ChatResult(answer=answer_text, citations=citations, retrieval_used=bool(citations))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def answer(question: str, course_id: str) -> ChatResult:
    """Hybrid RAG answer: dense (QVAC) + sparse (BM25) → RRF → FlashRank → parent context → LLM.

    Flow:
      1. /retrieve  topK=20 dense chunks from QVAC
      2. BM25 sparse search on local index
      3. RRF merge → unified top-20
      4. FlashRank cross-encoder rerank → top-5
      5. DB lookup of parent texts for top-5 child chunks
      6. /generate  with parent contexts → LLM answer
    Falls back to ChromaDB if QVAC is unavailable.
    """
    # 1. Dense retrieval
    try:
        resp = await _client.post(
            "/retrieve",
            json={"question": question, "workspace": course_id, "topK": _TOP_K_RETRIEVE},
        )
        resp.raise_for_status()
        dense_data = resp.json()
        dense_chunks: list[dict] = dense_data.get("chunks", [])
    except httpx.HTTPError as exc:
        logger.warning("QVAC /retrieve unavailable (%s) — trying ChromaDB fallback", exc)
        return _chroma_chat_result(question, course_id)

    if not dense_chunks:
        logger.info("QVAC returned 0 chunks for course '%s', trying ChromaDB fallback", course_id)
        fallback = _chroma_chat_result(question, course_id)
        if fallback.citations:
            return fallback

    # 2. BM25 sparse retrieval
    bm25_results = _bm25_search(question, course_id, top_k=_TOP_K_RETRIEVE)

    # 3. RRF merge
    dense_registry = {c["chunk_id"]: c for c in dense_chunks if c.get("chunk_id")}
    if bm25_results:
        merged_ids = _rrf_merge(dense_chunks, bm25_results, top_n=_TOP_K_RETRIEVE)
        merged_chunks = _resolve_merged(merged_ids, dense_registry, course_id)
    else:
        merged_chunks = dense_chunks[:_TOP_K_RETRIEVE]

    # 4. FlashRank rerank → top-5
    reranked = _rerank_sources(question, merged_chunks)

    # 5. Parent text lookup (async-safe: sync DB call via thread)
    parent_ids = list({c.get("parent_id", "") for c in reranked if c.get("parent_id")})
    parent_map: dict[str, dict] = await asyncio.to_thread(_load_parents_from_db, parent_ids)

    # 6. Build LLM context: use parent text when available (richer context window)
    context_blocks: list[dict] = []
    seen_parents: set[str] = set()
    for c in reranked:
        pid = c.get("parent_id", "")
        if pid and pid in parent_map and pid not in seen_parents:
            seen_parents.add(pid)
            context_blocks.append({"label": parent_map[pid]["label"], "text": parent_map[pid]["text"]})
        elif not pid or pid not in parent_map:
            context_blocks.append({"label": c.get("label", ""), "text": c.get("content", "")})

    if not context_blocks:
        context_blocks = [{"label": c.get("label", ""), "text": c.get("content", "")} for c in reranked]

    # 7. LLM generation with parent contexts
    answer_text = ""
    try:
        gen_resp = await _client.post(
            "/generate",
            json={"question": question, "context": context_blocks},
        )
        gen_resp.raise_for_status()
        answer_text = gen_resp.json().get("answer", "")
    except httpx.HTTPError as exc:
        logger.warning("QVAC /generate failed (%s) — returning first context block", exc)
        answer_text = context_blocks[0]["text"] if context_blocks else "Risposta non disponibile."

    # 8. Citations (child-level for precise source attribution)
    citations = [
        Citation(
            snippet=(c.get("content") or c.get("snippet", ""))[:200],
            score=c.get("score", 0.0),
            label=c.get("label", ""),
            page=c.get("page", 0),
            slide=c.get("slide", 0),
            section=c.get("section", ""),
            doc_id=c.get("doc_id", ""),
        )
        for c in reranked
    ]

    return ChatResult(answer=answer_text, citations=citations, retrieval_used=bool(reranked))
