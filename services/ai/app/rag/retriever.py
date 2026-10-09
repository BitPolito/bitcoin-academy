"""Unified retrieval pipeline: Dense (QVAC) + Sparse (BM25) → Fusion → Rerank → MMR → Expansion."""
import asyncio
import logging
import os
import httpx

from app.schemas.evidence_pack import EvidenceChunk, CitationAnchor

logger = logging.getLogger(__name__)

_TOP_K_RETRIEVE = int(os.getenv("RAG_RETRIEVE_K", "20"))
_TOP_K_GENERATE = int(os.getenv("RAG_TOP_K", "5"))

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
_client = httpx.AsyncClient(base_url=_QVAC_SERVICE_URL, timeout=60.0)

_chroma_db: dict = {}

def _chroma_retrieve(query: str, course_id: str, top_k: int) -> list[EvidenceChunk]:
    """Fallback dense retrieval using ChromaDB."""
    global _chroma_db
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        from fastembed import TextEmbedding

        if not _chroma_db:
            chroma_path = os.getenv("CHROMA_DB_PATH", "")
            if not chroma_path:
                return []
            client = chromadb.PersistentClient(
                path=chroma_path,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            cname = os.getenv("CHROMA_COLLECTION_NAME", "bitpolito_course")
            try:
                _chroma_db["collection"] = client.get_collection(cname)
            except Exception:
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
        return chunks
    except Exception as exc:
        logger.warning("ChromaDB fallback failed: %s", exc)
        _chroma_db = {}
        return []

def _qvac_dict_to_chunk(d: dict) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=d.get("chunk_id", ""),
        text=d.get("content", "") or d.get("text", "") or d.get("snippet", ""),
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
) -> tuple[list[EvidenceChunk], list[EvidenceChunk]]:
    """Execute the full RAG pipeline: Dense + Sparse → Fusion → Rerank → MMR → Expansion."""
    from app.services import hybrid_search, reranker, parent_expansion

    dense_chunks: list[EvidenceChunk] = []
    try:
        resp = await _client.post(
            "/retrieve",
            json={"question": retrieval_query, "workspace": course_id, "topK": _TOP_K_RETRIEVE},
        )
        resp.raise_for_status()
        dense_chunks = [_qvac_dict_to_chunk(d) for d in resp.json().get("chunks", []) if d.get("chunk_id")]
    except httpx.HTTPError as exc:
        logger.info("QVAC /retrieve unavailable (%s) — trying Chroma fallback", exc)
        dense_chunks = await asyncio.get_event_loop().run_in_executor(
            None, _chroma_retrieve, retrieval_query, course_id, _TOP_K_RETRIEVE
        )
        if not dense_chunks:
            raise

    bm25_hits = hybrid_search.bm25_search(question, course_id, top_k=_TOP_K_RETRIEVE)
    if bm25_hits:
        index_data = hybrid_search.load_bm25_index(course_id)
        corpus = index_data[2] if index_data else {}
        merged = hybrid_search.normalized_hybrid_fuse(
            dense_chunks, bm25_hits, corpus, top_k=_TOP_K_RETRIEVE
        )
    else:
        merged = dense_chunks[:_TOP_K_RETRIEVE]

    reranked_all = reranker.rerank(question, merged)
    reranked = reranker.mmr_select(reranked_all, _TOP_K_GENERATE)
    context_chunks = parent_expansion.expand_to_parents(reranked)

    return context_chunks, reranked