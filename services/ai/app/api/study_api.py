"""Study API — action-aware RAG endpoints."""
import asyncio
import json
import logging
from typing import List, Optional, Sequence

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse

from app.core.config import TokenPayload
from app.core.rate_limit import limiter
from app.db.session import get_db_context
from app.middleware.auth import get_current_user
from app.schemas.study_schemas import (
    STUDY_ACTION_REGISTRY,
    ActionMetaOut,
    CitationOut,
    StudyActionsResponse,
    StudyDispatchRequest,
    StudyDispatchResponse,
)
from app.schemas.study_session_schemas import TurnCitationOut
from app.services import study_service, study_session_service
from app.services.study_service import SourceChunk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Study"])

# Keepalive interval for SSE streams: emit a comment line if no token arrives within
# this many seconds. Prevents nginx/CloudFlare from closing idle connections (default 60 s).
_SSE_KEEPALIVE_INTERVAL = 15.0

# Mirrors study_service's private _CITATIONS_SENTINEL — duplicated rather than
# imported, same as tests/unit/test_streaming_dispatch.py does, since the two
# modules intentionally don't share private constants across the service boundary.
_CITATIONS_SENTINEL = "\x00CITATIONS\x00"


def _citation_out(c: SourceChunk) -> CitationOut:
    return CitationOut(
        snippet=c.snippet,
        score=c.score,
        label=c.label,
        page=c.page,
        slide=c.slide,
        section=c.section,
        doc_id=c.doc_id,
        chunk_id=c.chunk_id,
        chunk_type=c.chunk_type,
    )


def _persist_turn(
    user_id: str,
    session_id: str,
    action: str,
    query: str,
    answer: str,
    citations: Sequence[SourceChunk],
    duration_ms: Optional[float] = None,
) -> Optional[str]:
    """Append a turn to *session_id* if the caller passed one and owns it.

    Best-effort: a missing/foreign session_id is not an error for the study
    action itself (see StudyDispatchRequest.session_id), so any persistence
    failure here is logged and swallowed rather than propagated.
    """
    try:
        with get_db_context() as db:
            turn = study_session_service.append_turn(
                db,
                user_id,
                session_id,
                action=action,
                query=query,
                answer=answer,
                citations=[
                    TurnCitationOut(
                        doc_id=c.doc_id,
                        doc_name=c.label,
                        section=c.section or None,
                        page=c.page or None,
                        slide=c.slide or None,
                        chunk_id=c.chunk_id or None,
                        chunk_type=c.chunk_type or None,
                        snippet=c.snippet,
                    )
                    for c in citations
                ],
                duration_ms=int(duration_ms) if duration_ms is not None else None,
            )
            return turn.id if turn is not None else None
    except Exception:
        logger.warning("Failed to persist study turn for session %s", session_id, exc_info=True)
        return None


@router.post(
    "/courses/{course_id}/study",
    response_model=StudyDispatchResponse,
    responses={503: {"description": "Course search unavailable, timed out, or failed"}},
    summary="Run a study action on course material",
    description=(
        "Retrieves relevant passages and applies the requested study action "
        "(explain, summarize, retrieve, open_questions, quiz, oral, derive, compare). "
        "An empty search returns 200 with no citations. Retrieval failure returns "
        "503 with an error code and message; generation failure falls back to source passages."
    ),
)
@limiter.limit("20/minute")
async def study(
    request: Request,
    body: StudyDispatchRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyDispatchResponse:
    result = await study_service.dispatch(
        question=body.query,
        course_id=course_id,
        action=body.action,
        rag_only=body.rag_only,
    )

    turn_id = None
    if body.session_id:
        turn_id = _persist_turn(
            current_user.sub,
            body.session_id,
            action=body.action.value,
            query=body.query,
            answer=result.answer,
            citations=result.citations,
        )

    return StudyDispatchResponse(
        answer=result.answer,
        citations=[_citation_out(c) for c in result.citations],
        retrieval_used=result.retrieval_used,
        action=body.action.value,
        turn_id=turn_id,
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
        "Retrieval failure emits a '[ERROR] <message>' frame and then [DONE], "
        "without answer tokens or citations.\n"
        "Generation interrupted after partial output emits an [ERROR] frame and "
        "then [DONE]; the partial answer is not cached.\n"
        "SSE comment lines (': keepalive') are sent every 15 s during retrieval to\n"
        "prevent proxy timeouts. QUIZ and ORAL are buffered internally."
    ),
)
@limiter.limit("20/minute")
async def study_stream(
    request: Request,
    body: StudyDispatchRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    current_user: TokenPayload = Depends(get_current_user),
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
        # Accumulated once the stream completes normally (no error) — persisted
        # after [DONE] only on that path, mirroring study_service's own "the
        # partial answer is not cached" rule for interrupted streams (#136).
        answer_parts: List[str] = []
        citations: List[SourceChunk] = []
        completed = False
        # The next-token task is created once and awaited across keepalive ticks.
        # We must NOT wrap gen.__anext__() in asyncio.wait_for: a timeout there
        # cancels the in-flight step, which finishes the async generator and
        # ends the stream empty — exactly on the slow retrievals the keepalive
        # exists to cover. Instead we poll the same pending task with a timeout.
        pending: "asyncio.Future | None" = None
        try:
            while True:
                if pending is None:
                    pending = asyncio.ensure_future(gen.__anext__())
                done, _ = await asyncio.wait(
                    {pending}, timeout=_SSE_KEEPALIVE_INTERVAL
                )
                if not done:
                    # No token yet — send SSE comment to keep the connection alive.
                    # Browsers and SSE clients silently ignore comment lines.
                    yield ": keepalive\n\n"
                    continue
                try:
                    chunk = pending.result()
                except StopAsyncIteration:
                    completed = True
                    break
                finally:
                    pending = None
                if chunk.startswith(_CITATIONS_SENTINEL):
                    try:
                        citations = [
                            SourceChunk(**c)
                            for c in json.loads(chunk[len(_CITATIONS_SENTINEL):])
                        ]
                    except (ValueError, TypeError):
                        citations = []
                else:
                    answer_parts.append(chunk)
                yield f"data: {_sse_encode(chunk)}\n\n"
        except Exception as exc:
            yield f"data: {_sse_encode('[ERROR] ' + str(exc))}\n\n"
        finally:
            if pending is not None:
                pending.cancel()
                try:
                    await pending
                except (asyncio.CancelledError, StopAsyncIteration, Exception):
                    pass
            await gen.aclose()
        if completed and body.session_id and answer_parts:
            _persist_turn(
                current_user.sub,
                body.session_id,
                action=body.action.value,
                query=body.query,
                answer="".join(answer_parts),
                citations=citations,
            )
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
