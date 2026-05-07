"""Cross-encoder reranker — improves chunk ordering beyond vector similarity.

Uses `sentence-transformers` with the `cross-encoder/ms-marco-MiniLM-L-6-v2`
model (lightweight, ~100 MB, CPU-friendly, target <200 ms for 10 chunks).

Fails gracefully: if the model is unavailable (import error, OOM, first-run
download failure, etc.) chunks are returned in their original order and a
warning is logged.  This means the pipeline degrades to pure vector ranking
rather than crashing.
"""
import logging
from typing import List

from app.schemas.evidence_pack import EvidenceChunk

logger = logging.getLogger(__name__)

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Module-level singleton — loaded lazily on first call to rerank().
_model = None
_model_load_attempted = False


def _get_model():
    """Return the CrossEncoder model singleton, loading it on first call.

    Caches the result (including None on failure) so subsequent calls are fast.
    """
    global _model, _model_load_attempted
    if _model_load_attempted:
        return _model

    _model_load_attempted = True
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

        _model = CrossEncoder(_MODEL_NAME)
        logger.info("Cross-encoder reranker loaded: %s", _MODEL_NAME)
    except Exception as exc:
        logger.warning(
            "Cross-encoder unavailable — reranker disabled (vector order preserved): %s",
            exc,
        )
        _model = None

    return _model


def rerank(query: str, chunks: List[EvidenceChunk]) -> List[EvidenceChunk]:
    """Re-order chunks by cross-encoder relevance score.

    Sets `rerank_score` on each returned chunk.  The original `score` (vector
    similarity) is preserved unchanged for comparison and fallback sorting.

    Falls back to the original input order when the cross-encoder model is not
    available or inference raises an exception.

    Args:
        query: The student question.
        chunks: Candidate EvidenceChunks — typically deduped and boost-adjusted.

    Returns:
        Chunks sorted by rerank_score descending, or original order on failure.
    """
    if not chunks:
        return chunks

    model = _get_model()
    if model is None:
        return chunks  # graceful fallback — no reranking

    try:
        pairs = [(query, c.text) for c in chunks]
        raw_scores: list[float] = model.predict(pairs).tolist()

        reranked = sorted(
            [
                c.model_copy(update={"rerank_score": float(s)})
                for c, s in zip(chunks, raw_scores)
            ],
            key=lambda c: c.rerank_score,
            reverse=True,
        )

        logger.debug(
            "Reranker: %d chunks scored — top=%.4f, bottom=%.4f",
            len(reranked),
            reranked[0].rerank_score if reranked else 0.0,
            reranked[-1].rerank_score if reranked else 0.0,
        )
        return reranked

    except Exception as exc:
        logger.warning("Reranker inference failed — reverting to vector order: %s", exc)
        return chunks
