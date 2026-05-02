"""Study API — action-aware RAG endpoints."""
from typing import List

from fastapi import APIRouter, Depends, Path

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


@router.post(
    "/courses/{course_id}/study",
    response_model=StudyDispatchResponse,
    summary="Run a study action on course material",
    description=(
        "Retrieves relevant passages and applies the requested study action "
        "(explain, summarize, retrieve, open_questions, quiz, oral). "
        "Falls back gracefully when the QVAC service or LLM is unavailable."
    ),
)
async def study(
    body: StudyDispatchRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> StudyDispatchResponse:
    result = await study_service.dispatch(
        question=body.query,
        course_id=course_id,
        action=body.action,
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
