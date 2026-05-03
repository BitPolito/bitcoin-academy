"""Evidence pack service — reranks, deduplicates, and assembles EvidencePack."""
from app.schemas.evidence_pack import EvidenceChunk, EvidencePack
from app.services import retrieval_service

_TOP_EVIDENCE = 6


def build_from_chunks(
    query: str,
    action: str,
    candidates: list[EvidenceChunk],
) -> EvidencePack:
    """Assemble an EvidencePack from an already-retrieved list of EvidenceChunks.

    Shared by both the ChromaDB debug path (build()) and the QVAC production
    path in study_service, so dedup/boost logic stays in one place.
    """
    total = len(candidates)
    deduped = _deduplicate(candidates)
    boosted = _apply_boost(deduped, action)
    ranked = sorted(boosted, key=lambda c: c.score, reverse=True)[:_TOP_EVIDENCE]

    # ordering[i] = position of ranked[i] in the post-dedup list before boost-sort
    pre_sort_ids = [c.chunk_id for c in deduped]
    ordering = [
        pre_sort_ids.index(c.chunk_id) if c.chunk_id in pre_sort_ids else i
        for i, c in enumerate(ranked)
    ]

    return EvidencePack(
        query=query,
        action=action,
        chunks=ranked,
        total_candidates=total,
        ordering=ordering,
        deduped_passages=[c.text for c in ranked],
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
