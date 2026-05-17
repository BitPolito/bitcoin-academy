"""Feedback API — student thumbs-up/down ratings for RAG answers (Q8)."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from app.core.rate_limit import limiter
from app.db.models import AnswerFeedback
from app.db.session import get_db_context
from app.middleware.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["Feedback"])


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., max_length=128)
    question: str = Field(..., max_length=2000)
    answer: str = Field(..., max_length=10000)
    rating: int = Field(..., description="1 = helpful, -1 = not helpful")
    comment: Optional[str] = Field(default=None, max_length=1000)

    model_config = {"json_schema_extra": {"example": {"session_id": "abc123", "question": "What is UTXO?", "answer": "A UTXO is...", "rating": 1}}}


class FeedbackResponse(BaseModel):
    id: str
    status: str = "recorded"


@router.post(
    "/courses/{course_id}/chat/feedback",
    response_model=FeedbackResponse,
    summary="Submit feedback on a RAG answer",
)
@limiter.limit("30/minute")
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    course_id: str = Path(...),
    _current_user: CurrentUser = Depends(get_current_user),
) -> FeedbackResponse:
    if body.rating not in (1, -1):
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(status_code=422, detail="rating must be 1 or -1")

    with get_db_context() as db:
        record = AnswerFeedback(
            id=str(uuid.uuid4()),
            session_id=body.session_id,
            course_id=course_id,
            question=body.question,
            answer=body.answer,
            rating=body.rating,
            comment=body.comment,
        )
        db.add(record)
        db.commit()
        return FeedbackResponse(id=record.id)
