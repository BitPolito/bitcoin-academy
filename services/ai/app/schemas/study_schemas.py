"""Study action request/response schemas."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.evidence_pack import EvidencePack


class StudyAction(str, Enum):
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"
    RETRIEVE = "retrieve"
    OPEN_QUESTIONS = "open_questions"
    QUIZ = "quiz"
    ORAL = "oral"


class StudyRequest(BaseModel):
    action: StudyAction
    query: str = Field(..., min_length=1, max_length=2000)
    context: Optional[str] = None


class StudyResponse(BaseModel):
    action: StudyAction
    output: str
    evidence: EvidencePack
    retrieval_used: bool
