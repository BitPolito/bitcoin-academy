"""Unified retrieval pipeline shared by the chat and study paths.

Dense (QVAC, ChromaDB fallback) + sparse (BM25) -> normalized fusion ->
cross-encoder rerank -> MMR diversity -> parent context expansion.

Callers pass their own QVAC HTTP client so each keeps its own timeouts and
remains the single point tests patch. Caller-specific steps stay with the
caller: compression and token budgeting in chat_service, action boosting and
two-hop retrieval in study_service.
"""
import asyncio
import logging
import os

import httpx

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk

logger = logging.getLogger(__name__)

# RAG_RETRIEVE_K: total candidates fetched from dense + sparse pool.
# RAG_TOP_K: chunks kept after reranking and MMR (context window budget).
_TOP_K_RETRIEVE = int(os.getenv("RAG_RETRIEVE_K", "20"))
_TOP_K_GENERATE = int(os.getenv("RAG_TOP_K", "5"))

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


async def unified_retrieval(
    question: str,
    course_id: str,
    retrieval_query: str,
    *,
    client: httpx.AsyncClient,
) -> tuple[list[EvidenceChunk], list[EvidenceChunk]]:
    """Run the hybrid pipeline and return (context_chunks, reranked).

    *retrieval_query* (possibly rewritten) drives dense search; the original
    *question* drives BM25, reranking and MMR. *reranked* are the selected
    child chunks (citations); *context_chunks* are their parent-expanded form.

    Primary dense source: QVAC (GTE-Large embeddings).
    Fallback dense source: ChromaDB (all-MiniLM-L6-v2) when QVAC /retrieve is unavailable.
    Raises httpx.HTTPError only when BOTH sources fail.
    """

    from app.services import hybrid_search, reranker, parent_expansion  # noqa: PLC0415

    # ── Dense retrieval (QVAC primary → ChromaDB fallback) ───────────────────
    dense_chunks: list[EvidenceChunk] = []
    try:
        resp = await client.post(
            "/retrieve",
            json={"question": retrieval_query, "workspace": course_id, "topK": _TOP_K_RETRIEVE},
        )
        resp.raise_for_status()
        dense_chunks = [_qvac_dict_to_chunk(d) for d in resp.json().get("chunks", []) if d.get("chunk_id")]
    except httpx.HTTPError as exc:
        logger.info("QVAC /retrieve unavailable (%s) — trying ChromaDB fallback", exc)
        dense_chunks = await asyncio.get_running_loop().run_in_executor(
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

    return context_chunks, reranked
