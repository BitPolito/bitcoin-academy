"""Study API — action-aware RAG endpoints."""
import asyncio
import json
from typing import List

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse

from app.core.rate_limit import limiter
from app.middleware.auth import CurrentUser, get_current_user
from app.schemas.study_schemas import (
    STUDY_ACTION_REGISTRY,
    ActionMetaOut,
    CitationOut,
    StudyActionsResponse,
    StudyDispatchRequest,
    StudyDispatchResponse,
)
from app.services import study_service

router = APIRouter(prefix="/api", tags=["Study"])

# Keepalive interval for SSE streams: emit a comment line if no token arrives within
# this many seconds. Prevents nginx/CloudFlare from closing idle connections (default 60 s).
_SSE_KEEPALIVE_INTERVAL = 15.0


@router.post(
    "/courses/{course_id}/study",
    response_model=StudyDispatchResponse,
    summary="Run a study action on course material",
    description=(
        "Retrieves relevant passages and applies the requested study action "
        "(explain, summarize, retrieve, open_questions, quiz, oral, derive, compare). "
        "Falls back gracefully when the QVAC service or LLM is unavailable."
    ),
)
@limiter.limit("20/minute")
async def study(
    request: Request,
    body: StudyDispatchRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> StudyDispatchResponse:
    result = await study_service.dispatch(
        question=body.query,
        course_id=course_id,
        action=body.action,
        rag_only=body.rag_only,
    )
    return StudyDispatchResponse(
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
        action=body.action.value,
    )


@router.post(
    "/courses/{course_id}/study/stream",
    summary="Stream a study action on course material (SSE)",
    description=(
        "Same as POST /study but returns a Server-Sent Events stream.\n"
        "Tokens are emitted as 'data: <json-string>\\n\\n'.\n"
        "After the last token, a citations sentinel is emitted:\n"
        "  'data: \"\\x00CITATIONS\\x00<json-array>\"\\n\\n'\n"
        "followed by 'data: [DONE]\\n\\n'.\n"
        "SSE comment lines (': keepalive') are sent every 15 s during retrieval to\n"
        "prevent proxy timeouts. QUIZ and ORAL are buffered internally."
    ),
)
@limiter.limit("20/minute")
async def study_stream(
    request: Request,
    body: StudyDispatchRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    async def _event_generator():
        # Drive the async generator manually so we can interleave keepalive comments
        # when no token arrives within _SSE_KEEPALIVE_INTERVAL seconds.
        # This prevents nginx/CloudFlare from closing the connection during the
        # retrieval phase (which can take 20-40 s on limited hardware).
        gen = study_service.stream_dispatch(
            question=body.query,
            course_id=course_id,
            action=body.action,
            rag_only=body.rag_only,
        )
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        gen.__anext__(), timeout=_SSE_KEEPALIVE_INTERVAL
                    )
                    yield f"data: {_sse_encode(chunk)}\n\n"
                except asyncio.TimeoutError:
                    # No token yet — send SSE comment to keep TCP connection alive.
                    # Browsers and SSE clients silently ignore comment lines.
                    yield ": keepalive\n\n"
                except StopAsyncIteration:
                    break
        except Exception as exc:
            yield f"data: {_sse_encode('[ERROR] ' + str(exc))}\n\n"
        finally:
            await gen.aclose()
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx proxy buffering
        },
    )


def _sse_encode(value: str) -> str:
    return json.dumps(value)


@router.get(
    "/study/actions",
    response_model=StudyActionsResponse,
    summary="List available study actions",
    description="Returns the full STUDY_ACTION_REGISTRY — useful for dynamic frontend rendering.",
)
def list_study_actions() -> StudyActionsResponse:
    actions: List[ActionMetaOut] = [
        ActionMetaOut(
            action=action.value,
            name=meta.name,
            description=meta.description,
            retrieval_required=meta.retrieval_required,
            generation_required=meta.generation_required,
            output_type=meta.output_type,
            source_grounding_required=meta.source_grounding_required,
            example_query=meta.example_query,
        )
        for action, meta in STUDY_ACTION_REGISTRY.items()
    ]
    return StudyActionsResponse(actions=actions)
