"""ChromaDB fallback retrieval — used when QVAC returns zero results.

Returns source dicts with the same shape as QVAC /query sources so callers
can build EvidenceChunk / Citation objects without branching.
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
_SERVICES_AI = _HERE.parents[2]   # services/ai/

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(_SERVICES_AI / "chroma_db"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "bitpolito_course")


def query_chroma(question: str, course_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Query ChromaDB for chunks matching *question*, filtered to *course_id*.

    Returns a list of source dicts:
        {snippet, score, label, page, slide, section, doc_id}

    Cosine distance [0, 2] is converted to similarity score [1, 0] via
    score = max(0.0, 1.0 - distance).  Returns [] on any error so callers
    can treat this as a graceful no-op.
    """
    try:
        from fastembed import TextEmbedding          # noqa: PLC0415
        import chromadb                              # noqa: PLC0415
        from chromadb.config import Settings as ChromaSettings  # noqa: PLC0415

        client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
        query_vec = [v.tolist() for v in model.embed([question])][0]

        results = collection.query(
            query_embeddings=[query_vec],
            n_results=top_k,
            where={"course_id": course_id},
            include=["documents", "metadatas", "distances"],
        )

        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        sources = []
        for text, meta, dist in zip(docs, metas, distances):
            sources.append({
                "snippet": text,
                "score": max(0.0, 1.0 - float(dist)),
                "label": meta.get("label", ""),
                "page": int(meta.get("page", 0)),  # type: ignore[arg-type]
                "slide": int(meta.get("slide", 0)),  # type: ignore[arg-type]
                "section": meta.get("section", ""),
                "doc_id": meta.get("doc_id", ""),
            })

        logger.info(
            "ChromaDB fallback returned %d chunks for course '%s'",
            len(sources), course_id,
        )
        return sources

    except Exception as exc:
        logger.warning("ChromaDB fallback query failed: %s", exc)
        return []
