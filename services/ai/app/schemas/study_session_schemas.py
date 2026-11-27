"""Study session schemas — DTOs for persisted study history (issue #136)."""
from typing import List, Optional

from pydantic import BaseModel


class TurnCitationOut(BaseModel):
    """A citation anchor stored on a turn — enough to resolve back to a chunk."""

    doc_id: str
    doc_name: str = ""
    section: Optional[str] = None
    page: Optional[int] = None
    slide: Optional[int] = None
    chunk_id: Optional[str] = None
    chunk_type: Optional[str] = None
    snippet: str = ""


class StudyTurnOut(BaseModel):
    id: str
    action: str
    query: str
    answer: str
    citations: List[TurnCitationOut]
    duration_ms: Optional[int] = None
    model_tier: Optional[str] = None
    created_at: str


class StudySessionOut(BaseModel):
    id: str
    course_id: str
    title: Optional[str] = None
    started_at: str
    last_active_at: str
    turn_count: int = 0


class StudySessionDetailOut(StudySessionOut):
    turns: List[StudyTurnOut]
