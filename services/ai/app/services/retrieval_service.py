"""Retrieval service — queries ChromaDB with course_id filter, returns EvidenceChunks."""
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


def search(
    query: str,
    course_id: str,
    top_k: int = 10,
    min_score: float = 0.4,
) -> list[EvidenceChunk]:
    """Return EvidenceChunks matching query filtered to course_id.

    Args:
        query: Student question — stripped and truncated to 300 chars before embedding.
        course_id: Only chunks belonging to this course are returned.
        top_k: Maximum number of candidates to retrieve from ChromaDB.
        min_score: Cosine-similarity threshold; chunks below this value are discarded
            (default 0.4 — calibrate on real course documents).

    Returns empty list on any error so callers can degrade gracefully.
    """
    # Preprocess query: strip whitespace, cap length to avoid oversized embeddings
    clean_query = query.strip()[:300]
    # Sanitize ligature corruption (same fix as in VerilocalSearcher)
    clean_query = clean_query.replace("昀椀", "fi").replace("昀氀", "fl")

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

        chunks: list[EvidenceChunk] = []
        if not results or not results.get("ids") or not results["ids"]:
            return []
        ids = results["ids"][0]
        docs = (results["documents"] or [[]])[0]
        metas = (results["metadatas"] or [[]])[0]
        dists = (results["distances"] or [[]])[0]

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

        filtered = [c for c in chunks if c.score >= min_score]
        if len(filtered) < len(chunks):
            logger.debug(
                "min_score=%.2f discarded %d/%d chunks for course_id=%s",
                min_score,
                len(chunks) - len(filtered),
                len(chunks),
                course_id,
            )
        return filtered

    except Exception as exc:
        logger.warning("Retrieval failed for course_id=%s: %s", course_id, exc)
        return []
