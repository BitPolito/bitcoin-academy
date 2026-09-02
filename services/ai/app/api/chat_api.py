"""Chat API controller - RAG-backed Q&A endpoint."""
import asyncio
import json
from typing import AsyncGenerator, List

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.middleware.auth import CurrentUser, get_current_user
from app.services import chat_service
from app.core.rate_limit import limiter

router = APIRouter(prefix="/api", tags=["Chat"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class HistoryEntry(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Student question (min 5 characters)",
    )
    history: List[HistoryEntry] = Field(
        default_factory=list,
        max_length=10,
        description="Previous conversation turns (up to 10 messages)",
    )


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
    history = [{"role": h.role, "content": h.content} for h in body.history]
    result = await chat_service.answer(question=body.message, course_id=course_id, history=history)
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


@router.post(
    "/courses/{course_id}/chat/stream",
    summary="Stream a RAG answer token-by-token (SSE)",
    description=(
        "Same retrieval pipeline as /chat but returns a Server-Sent Events stream. "
        "Each event is 'data: <token>\\n\\n'. A final 'data: [CITATIONS]<json>\\n\\n' "
        "event delivers citation metadata after all tokens. Ends with 'data: [DONE]\\n\\n'."
    ),
)
@limiter.limit("20/minute")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    history = [{"role": h.role, "content": h.content} for h in body.history]

    _HEARTBEAT_INTERVAL = 15.0  # seconds between keep-alive comments

    async def event_generator() -> AsyncGenerator[str, None]:
        stream_iter = chat_service.stream_answer(
            question=body.message, course_id=course_id, history=history
        ).__aiter__()
        # Keep a persistent Task so asyncio.wait_for timeout does NOT cancel the
        # underlying generator — only the shield wrapper is cancelled on timeout.
        pending: asyncio.Task | None = None
        while True:
            try:
                if pending is None:
                    pending = asyncio.ensure_future(stream_iter.__anext__())
                chunk = await asyncio.wait_for(asyncio.shield(pending), timeout=_HEARTBEAT_INTERVAL)
                pending = None  # consumed — create a new task next iteration
                if chunk.startswith("\x00CITATIONS\x00"):
                    citations_json = chunk[len("\x00CITATIONS\x00"):]
                    yield f"data: [CITATIONS]{citations_json}\n\n"
                else:
                    yield f"data: {json.dumps(chunk)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                # pending task is still running in background — loop and wait again
            except StopAsyncIteration:
                break
        if pending is not None:
            pending.cancel()
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
