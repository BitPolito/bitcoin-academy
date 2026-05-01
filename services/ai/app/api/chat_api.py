"""Chat API controller - RAG-backed Q&A endpoint."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from app.middleware.auth import CurrentUser, get_current_user
from app.services import chat_service

router = APIRouter(prefix="/api", tags=["Chat"])


# ---------------------------------------------------------------------------
# Request / Response schemas (inline — chat is self-contained)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="Student question")


class CitationOut(BaseModel):
    label: str
    section: Optional[str] = None
    page: Optional[int] = None
    slide: Optional[int] = None
    text_snippet: str


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
        "Retrieves relevant passages from the indexed course documents and "
        "synthesises an answer. Requires a valid JWT. "
        "Falls back to raw context when no OpenAI key is configured."
    ),
)
def chat(
    body: ChatRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    result = chat_service.answer(question=body.message, course_id=course_id)
    return ChatResponse(
        answer=result.answer,
        citations=[
            CitationOut(
                label=c.label,
                section=c.section,
                page=c.page,
                slide=c.slide,
                text_snippet=c.text_snippet,
            )
            for c in result.citations
        ],
        retrieval_used=result.retrieval_used,
    )
