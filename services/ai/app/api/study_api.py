"""Study API — dispatches explicit study actions backed by RAG retrieval."""
import logging

from fastapi import APIRouter, Depends, Path

from app.middleware.auth import CurrentUser, get_current_user
from app.schemas.study_schemas import StudyRequest, StudyResponse
from app.services import study_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Study"])


@router.post(
    "/courses/{course_id}/study",
    response_model=StudyResponse,
    summary="Run a study action on course materials",
    description=(
        "Retrieves relevant passages from the course's indexed documents, "
        "assembles an evidence pack, and—when an LLM is configured—generates "
        "a source-grounded study output. Supported actions: explain, summarize, "
        "retrieve, open_questions, quiz, oral."
    ),
)
def study(
    body: StudyRequest,
    course_id: str = Path(..., description="Course whose documents to search"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> StudyResponse:
    try:
        return study_service.dispatch(body, course_id)
    except Exception as exc:
        logger.warning("Study action failed for course %s: %s", course_id, exc)
        from app.schemas.evidence_pack import EvidencePack
        return StudyResponse(
            action=body.action,
            output="",
            evidence=EvidencePack(
                query=body.query,
                action=body.action,
                chunks=[],
                total_candidates=0,
            ),
            retrieval_used=False,
        )
