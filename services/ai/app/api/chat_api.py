"""Chat API controller - RAG-backed Q&A endpoint."""
from typing import List

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from app.middleware.auth import CurrentUser, get_current_user
from app.services import chat_service
from app.core.rate_limit import limiter

router = APIRouter(prefix="/api", tags=["Chat"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="Student question")


class CitationOut(BaseModel):
    snippet: str
    score: float
    label: str = ""
    page: int = 0
    slide: int = 0
    section: str = ""
    doc_id: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationOut]
    retrieval_used: bool


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/chat",
    response_model=ChatResponse,
    summary="Ask a question about course materials",
    description=(
        "Retrieves relevant passages from the indexed course documents via the "
        "QVAC service and synthesises an answer. Requires a valid JWT. "
        "Falls back to a plain message when the QVAC service is unavailable."
    ),
)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    result = await chat_service.answer(question=body.message, course_id=course_id)
    return ChatResponse(
        answer=result.answer,
        citations=[
            CitationOut(
                snippet=c.snippet,
                score=c.score,
                label=c.label,
                page=c.page,
                slide=c.slide,
                section=c.section,
                doc_id=c.doc_id,
            )
            for c in result.citations
        ],
        retrieval_used=result.retrieval_used,
    )
