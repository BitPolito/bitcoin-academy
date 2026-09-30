"""Cross-encoder reranker — flashrank (primary) with sentence-transformers fallback.

Flashrank is CPU-optimized and significantly faster than CrossEncoder for typical
batch sizes (≤10 chunks). Both backends fail gracefully: chunks are returned in
vector-score order when neither is available.

Model choices:
  flashrank   : ms-marco-MiniLM-L-12-v2  (~60 MB, 12-layer, better accuracy)
  CrossEncoder: ms-marco-MiniLM-L-6-v2   (~80 MB, 6-layer, sentence-transformers)
"""
import logging
from typing import List

from app.schemas.evidence_pack import EvidenceChunk

logger = logging.getLogger(__name__)

_FLASHRANK_MODEL = "ms-marco-MiniLM-L-12-v2"
_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_FLASHRANK_CACHE = "/tmp/flashrank"
_MMR_EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_flashrank_ranker = None
_flashrank_attempted = False
_cross_encoder = None
_cross_encoder_attempted = False
_mmr_emb = None
_mmr_emb_attempted = False


def _get_flashrank():
    global _flashrank_ranker, _flashrank_attempted
    if _flashrank_attempted:
        return _flashrank_ranker
    _flashrank_attempted = True
    try:
        from flashrank import Ranker
        _flashrank_ranker = Ranker(model_name=_FLASHRANK_MODEL, cache_dir=_FLASHRANK_CACHE)
        logger.info("Flashrank reranker loaded: %s", _FLASHRANK_MODEL)
    except Exception as exc:
        logger.warning("Flashrank unavailable — will try CrossEncoder: %s", exc)
        _flashrank_ranker = None
    return _flashrank_ranker


def _get_cross_encoder():
    global _cross_encoder, _cross_encoder_attempted
    if _cross_encoder_attempted:
        return _cross_encoder
    _cross_encoder_attempted = True
    try:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder(_CROSS_ENCODER_MODEL)
        logger.info("CrossEncoder fallback loaded: %s", _CROSS_ENCODER_MODEL)
    except Exception as exc:
        logger.warning(
            "CrossEncoder unavailable — reranker disabled (vector order preserved): %s", exc
        )
        _cross_encoder = None
    return _cross_encoder


def rerank(query: str, chunks: List[EvidenceChunk]) -> List[EvidenceChunk]:
    """Re-order chunks by cross-encoder relevance score.

    Sets `rerank_score` on each returned chunk. The original `score` (vector
    similarity or RRF) is preserved unchanged for comparison.

    Tries flashrank first; falls back to sentence-transformers CrossEncoder;
    returns chunks in original order when both are unavailable.

    Args:
        query:  The student question.
        chunks: Candidate EvidenceChunks — typically deduped and boost-adjusted.

    Returns:
        Chunks sorted by rerank_score descending, or original order on failure.
    """
    if not chunks:
        return chunks

    # --- flashrank (primary, CPU-optimized) ---
    ranker = _get_flashrank()
    if ranker is not None:
        try:
            from flashrank import RerankRequest
            request = RerankRequest(
                query=query,
                passages=[{"id": i, "text": c.text} for i, c in enumerate(chunks)],
            )
            results = ranker.rerank(request)
            # results: list[dict] with "id" (original index) and "score"
            id_to_score = {int(r["id"]): float(r["score"]) for r in results}
            reranked = sorted(
                [
                    c.model_copy(update={"rerank_score": id_to_score.get(i, 0.0)})
                    for i, c in enumerate(chunks)
                ],
                key=lambda c: c.rerank_score,
                reverse=True,
            )
            logger.debug(
                "Flashrank: %d chunks scored — top=%.4f, bottom=%.4f",
                len(reranked),
                reranked[0].rerank_score if reranked else 0.0,
                reranked[-1].rerank_score if reranked else 0.0,
            )
            return reranked
        except Exception as exc:
            logger.warning("Flashrank inference failed — trying CrossEncoder: %s", exc)

    # --- CrossEncoder (fallback) ---
    model = _get_cross_encoder()
    if model is not None:
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
                "CrossEncoder: %d chunks scored — top=%.4f, bottom=%.4f",
                len(reranked),
                reranked[0].rerank_score if reranked else 0.0,
                reranked[-1].rerank_score if reranked else 0.0,
            )
            return reranked
        except Exception as exc:
            logger.warning("CrossEncoder inference failed — reverting to vector order: %s", exc)

    return chunks


def _get_mmr_emb():
    global _mmr_emb, _mmr_emb_attempted
    if _mmr_emb_attempted:
        return _mmr_emb
    _mmr_emb_attempted = True
    try:
        from fastembed import TextEmbedding
        _mmr_emb = TextEmbedding(_MMR_EMB_MODEL)
        logger.info("MMR embedding model loaded: %s", _MMR_EMB_MODEL)
    except Exception as exc:
        logger.warning("MMR fastembed unavailable (%s) — mmr_select will use top-k fallback", exc)
        _mmr_emb = None
    return _mmr_emb


def mmr_select(chunks: List[EvidenceChunk], top_k: int, lambda_: float = 0.6) -> List[EvidenceChunk]:
    """Select top_k chunks using Maximum Marginal Relevance post-reranking.

    Penalises candidates that are semantically redundant with already-selected
    chunks, so the LLM receives diverse context instead of five near-identical
    passages from adjacent pages.

    Args:
        chunks:  Chunks sorted by rerank_score (output of rerank()).
        top_k:   Number of chunks to return.
        lambda_: 1.0 = pure relevance, 0.0 = pure diversity. 0.6 is a safe default.
    """
    if not chunks or top_k >= len(chunks):
        return chunks[:top_k]

    import numpy as np

    model = _get_mmr_emb()
    if model is None:
        return chunks[:top_k]

    try:
        embs = [np.asarray(e, dtype=float) for e in model.embed([c.text for c in chunks])]
    except Exception as exc:
        logger.warning("MMR embed failed (%s) — fallback to top-k slice", exc)
        return chunks[:top_k]

    # Use rerank_score when available; fall back to vector score when reranker did not run.
    use_rerank = any(c.rerank_score != 0.0 for c in chunks)

    def relevance(i: int) -> float:
        return chunks[i].rerank_score if use_rerank else chunks[i].score

    selected: list[int] = []
    remaining = list(range(len(chunks)))

    while remaining and len(selected) < top_k:
        if not selected:
            best = max(remaining, key=relevance)
        else:
            sel_embs = [embs[j] for j in selected]

            def mmr_score(i: int, _sel: list = sel_embs) -> float:
                a = embs[i]
                norm_a = float(np.linalg.norm(a)) + 1e-8
                sims = [
                    float(np.dot(a, b) / (norm_a * (float(np.linalg.norm(b)) + 1e-8)))
                    for b in _sel
                ]
                return lambda_ * relevance(i) - (1 - lambda_) * max(sims)

            best = max(remaining, key=mmr_score)

        selected.append(best)
        remaining.remove(best)

    logger.debug("MMR: selected %d/%d chunks (lambda=%.1f)", len(selected), len(chunks), lambda_)
    return [chunks[i] for i in selected]
