"""Evidence pack — structured retrieval context passed to study action handlers."""
from typing import Optional
from pydantic import BaseModel


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
    anchor: CitationAnchor


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

    def context_block(self) -> str:
        """Numbered context string for LLM generation prompts."""
        if not self.deduped_passages:
            return ""
        return "\n\n---\n\n".join(
            f"[{i + 1}] {text}" for i, text in enumerate(self.deduped_passages)
        )
