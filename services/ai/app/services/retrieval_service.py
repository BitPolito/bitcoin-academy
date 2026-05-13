"""Retrieval service — hybrid dense+sparse search with RRF fusion.

Query path:
  1. Dense vector search via ChromaDB (fastembed/MiniLM-L6).
  2. Sparse BM25 search via pre-built per-course index (rank_bm25).
  3. Reciprocal Rank Fusion (k=60) merges both rankings.
  Falls back to dense-only when the BM25 index is absent.
"""
import logging
import os
from functools import lru_cache
from pathlib import Path

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
_SERVICES_AI = _HERE.parents[2]
_CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(_SERVICES_AI / "chroma_db"))
_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "bitpolito_course")

logger.info("ChromaDB path: %s | collection: %s", _CHROMA_DB_PATH, _COLLECTION_NAME)


@lru_cache(maxsize=1)
def _get_embedding_model():
    from fastembed import TextEmbedding
    return TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _get_collection():
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    os.makedirs(_CHROMA_DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(
        path=_CHROMA_DB_PATH,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _dense_search(
    clean_query: str,
    course_id: str,
    top_k: int,
) -> list[EvidenceChunk]:
    """ChromaDB vector search — internal helper, expects pre-processed query.

    Returns all results without a score threshold so RRF has full ranking signal.
    """
    try:
        model = _get_embedding_model()
        collection = _get_collection()

        if collection.count() == 0:
            logger.debug("ChromaDB collection is empty — no results")
            return []

        query_vector = list(model.embed([clean_query]))[0].tolist()
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, collection.count()),
            where={"course_id": course_id},
        )

        if not results or not results.get("ids") or not results["ids"]:
            return []

        ids = results["ids"][0]
        docs = (results["documents"] or [[]])[0]
        metas = (results["metadatas"] or [[]])[0]
        dists = (results["distances"] or [[]])[0]

        chunks: list[EvidenceChunk] = []
        for i in range(len(ids)):
            meta: dict = metas[i]  # type: ignore[assignment]
            distance: float = float(dists[i])  # type: ignore[arg-type]
            score = round(max(0.0, min(1.0, 1.0 - distance)), 4)

            page_raw = meta.get("page", 0)
            slide_raw = meta.get("slide", 0)
            page_int = int(page_raw) if page_raw else 0
            slide_int = int(slide_raw) if slide_raw else 0

            chunks.append(
                EvidenceChunk(
                    chunk_id=str(ids[i]),
                    text=str(docs[i]),
                    score=score,
                    anchor=CitationAnchor(
                        doc_id=str(meta.get("doc_id", "")),
                        doc_name=str(meta.get("filename") or meta.get("doc_id", "")),
                        section=str(meta["section"]) if meta.get("section") else None,
                        page=page_int if page_int > 0 else None,
                        slide=slide_int if slide_int > 0 else None,
                        chunk_id=str(ids[i]),
                        chunk_type=str(meta.get("chunk_type", "paragraph")),
                    ),
                )
            )
        return chunks

    except Exception as exc:
        logger.warning("Dense retrieval failed for course_id=%s: %s", course_id, exc)
        return []


def search(
    query: str,
    course_id: str,
    top_k: int = 10,
    min_score: float = 0.4,
) -> list[EvidenceChunk]:
    """Hybrid dense+sparse retrieval with RRF fusion.

    Runs ChromaDB vector search and BM25 sparse search, then fuses rankings
    via Reciprocal Rank Fusion (k=60). Falls back to dense-only retrieval when
    the BM25 index has not been built yet for this course.

    The min_score threshold applies only to the dense-only fallback path
    (cosine-similarity scale). Hybrid RRF scores are on a different scale
    (~0–0.033); quality filtering is delegated to the reranker instead.

    Args:
        query:      Student question; stripped and truncated to 300 chars.
        course_id:  Only chunks belonging to this course are returned.
        top_k:      Maximum number of results to return.
        min_score:  Cosine-similarity lower bound — dense-only fallback only.

    Returns [] on any error so callers can degrade gracefully.
    """
    from app.services.hybrid_search import bm25_search, load_bm25_index, rrf_fuse

    clean_query = query.strip()[:300].replace("昀椀", "fi").replace("昀氀", "fl")

    # Fetch 3× candidates so RRF has enough ranking signal from both sources
    candidate_k = top_k * 3

    dense_chunks = _dense_search(clean_query, course_id, top_k=candidate_k)
    bm25_hits = bm25_search(clean_query, course_id, top_k=candidate_k)

    if not bm25_hits:
        # Dense-only fallback — apply cosine similarity threshold
        logger.debug("BM25 index absent for course '%s' — dense-only retrieval", course_id)
        filtered = [c for c in dense_chunks[:top_k] if c.score >= min_score]
        if len(filtered) < len(dense_chunks[:top_k]):
            logger.debug(
                "min_score=%.2f discarded %d/%d chunks for course_id=%s",
                min_score,
                len(dense_chunks[:top_k]) - len(filtered),
                len(dense_chunks[:top_k]),
                course_id,
            )
        return filtered

    # Hybrid path — load corpus to reconstruct BM25-only chunk metadata
    index_data = load_bm25_index(course_id)
    corpus = index_data[2] if index_data else {}

    merged = rrf_fuse(dense_chunks, bm25_hits, corpus, top_k=top_k)
    logger.debug(
        "Hybrid search: %d results for course_id=%s", len(merged), course_id
    )
    return merged
