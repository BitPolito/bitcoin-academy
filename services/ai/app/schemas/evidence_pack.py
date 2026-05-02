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
    chunks: list[EvidenceChunk]
    total_candidates: int
