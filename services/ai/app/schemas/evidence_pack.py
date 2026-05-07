"""Evidence pack — structured retrieval context passed to study action handlers."""
from typing import Optional
from pydantic import BaseModel, computed_field


class CitationAnchor(BaseModel):
    doc_id: str
    doc_name: str
    section: Optional[str] = None
    page: Optional[int] = None
    slide: Optional[int] = None
    chunk_id: str
    chunk_type: str


class EvidenceChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    """Vector similarity score in [0, 1] — produced by the embedding model."""
    rerank_score: float = 0.0
    """Cross-encoder reranking score. 0.0 means the reranker was not run."""
    anchor: CitationAnchor

    @computed_field  # type: ignore[prop-decorator]
    @property
    def similarity_score(self) -> float:
        """Explicit alias for score — makes the semantic clearer in downstream code."""
        return self.score


class EvidencePack(BaseModel):
    query: str
    action: str
    # Ranked, deduplicated chunks selected for downstream consumption.
    chunks: list[EvidenceChunk]
    # How many raw candidates were considered before dedup/rerank.
    total_candidates: int
    # Positional rank: ordering[i] is the original pre-boost index of chunks[i].
    # Kept explicit so orchestrators can detect reordering without re-sorting.
    ordering: list[int]
    # Deduplicated text passages in rank order — ready for LLM context injection.
    deduped_passages: list[str]
    # Estimated token count of the evidence pack (len(text) // 4 heuristic).
    total_tokens_estimate: int = 0
    # True when the pack was cut short due to the max_tokens budget.
    truncated: bool = False
    # Unique source document names present in the pack, in rank order.
    sources: list[str] = []

    def context_block(self) -> str:
        """Numbered context string for LLM generation prompts.

        Uses [ref_N] markers so the LLM can cite specific sources in its answer.
        """
        if not self.deduped_passages:
            return ""
        return "\n\n---\n\n".join(
            f"[ref_{i + 1}] {text}" for i, text in enumerate(self.deduped_passages)
        )
