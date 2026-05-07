"""Evidence pack service — reranks, deduplicates, and assembles EvidencePack."""
import logging

from app.schemas.evidence_pack import EvidenceChunk, EvidencePack
from app.services import retrieval_service

logger = logging.getLogger(__name__)

_TOP_EVIDENCE = 6
_MAX_TOKENS = 2000


def _token_estimate(text: str) -> int:
    """Rough token count heuristic: 4 characters ≈ 1 token."""
    return len(text) // 4


def build_from_chunks(
    query: str,
    action: str,
    candidates: list[EvidenceChunk],
    max_tokens: int = _MAX_TOKENS,
) -> EvidencePack:
    """Assemble an EvidencePack from an already-retrieved list of EvidenceChunks.

    Pipeline: deduplicate → boost (action-specific) → rerank → token-truncate.

    Shared by both the ChromaDB debug path (build()) and the QVAC production
    path in study_service, so dedup/boost/rerank logic stays in one place.
    """
    total = len(candidates)
    deduped = _deduplicate(candidates)
    boosted = _apply_boost(deduped, action)

    # Reranking: cross-encoder improves ordering beyond vector similarity.
    # Imported lazily to avoid circular imports and to allow graceful fallback.
    from app.services import reranker as _reranker
    reranked = _reranker.rerank(query, boosted)

    # Sort by rerank_score when available (cross-encoder scale), else by vector score.
    has_rerank = any(c.rerank_score != 0.0 for c in reranked)
    if has_rerank:
        sorted_candidates = sorted(reranked, key=lambda c: c.rerank_score, reverse=True)
    else:
        sorted_candidates = sorted(reranked, key=lambda c: c.score, reverse=True)

    # Token-aware truncation: take up to _TOP_EVIDENCE chunks but stop when
    # cumulative token estimate exceeds max_tokens.
    selected: list[EvidenceChunk] = []
    token_sum = 0
    truncated = False
    for chunk in sorted_candidates[:_TOP_EVIDENCE]:
        est = _token_estimate(chunk.text)
        if token_sum + est > max_tokens and selected:
            truncated = True
            logger.debug(
                "Evidence pack truncated at %d chunks (%d tokens) — max_tokens=%d",
                len(selected),
                token_sum,
                max_tokens,
            )
            break
        selected.append(chunk)
        token_sum += est

    ranked = selected

    # ordering[i] = position of ranked[i] in the post-dedup list before rerank/sort
    pre_sort_ids = [c.chunk_id for c in deduped]
    ordering = [
        pre_sort_ids.index(c.chunk_id) if c.chunk_id in pre_sort_ids else i
        for i, c in enumerate(ranked)
    ]

    # Unique source names in rank order (preserves ordering, removes duplicates)
    sources = list(dict.fromkeys(c.anchor.doc_name for c in ranked))

    return EvidencePack(
        query=query,
        action=action,
        chunks=ranked,
        total_candidates=total,
        ordering=ordering,
        deduped_passages=[c.text for c in ranked],
        total_tokens_estimate=token_sum,
        truncated=truncated,
        sources=sources,
    )


def build(query: str, action: str, course_id: str, top_k: int = 10) -> EvidencePack:
    """Build from ChromaDB — used by the debug API endpoint."""
    candidates = retrieval_service.search(query, course_id, top_k=top_k)
    return build_from_chunks(query, action, candidates)


def _deduplicate(chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
    seen: set[str] = set()
    result = []
    for c in chunks:
        if c.chunk_id not in seen:
            seen.add(c.chunk_id)
            result.append(c)
    return result


def _apply_boost(chunks: list[EvidenceChunk], action: str) -> list[EvidenceChunk]:
    if action not in ("quiz", "oral"):
        return chunks
    return [
        c.model_copy(update={"score": min(round(c.score * 1.2, 4), 1.0)})
        if c.anchor.chunk_type == "past_exam"
        else c
        for c in chunks
    ]
