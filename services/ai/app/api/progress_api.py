"""Progress API controller - HTTP + error mapping."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.config import TokenPayload
from app.core.errors import NotFoundError, ValidationError_
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.progress_schemas import (
    BadgeResponse,
    CourseProgressResponse,
    ProgressUpdateResult,
    UpdateLessonProgressRequest,
    UserBadgeResponse,
)
from app.services import progress_service

router = APIRouter(prefix="/api", tags=["Progress"])


def _validate_uuid(value: str, field: str) -> None:
    try:
        UUID(value)
    except ValueError:
        raise ValidationError_(
            message=f"Invalid {field} format. Expected UUID.",
            details={field: value},
        )


@router.get("/progress/{course_id}", response_model=CourseProgressResponse)
def get_course_progress(
    course_id: str = Path(min_length=1, max_length=36),
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> CourseProgressResponse:
    """Get the current user's progress for a specific course."""
    _validate_uuid(course_id, "course_id")
    return progress_service.get_course_progress(db, current_user.sub, course_id)


@router.post("/progress/update", response_model=ProgressUpdateResult)
def update_progress(
    body: UpdateLessonProgressRequest,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ProgressUpdateResult:
    """Update lesson progress and recalculate course progress.

    Returns updated progress and any newly awarded badges.
    """
    _validate_uuid(body.lesson_id, "lesson_id")
    _validate_uuid(body.course_id, "course_id")
    return progress_service.update_lesson_progress(
        db=db,
        user_id=current_user.sub,
        lesson_id=body.lesson_id,
        course_id=body.course_id,
        status=body.status.value,
        score=body.score,
    )


@router.get("/badges", response_model=List[BadgeResponse])
def list_badges(
    db: Session = Depends(get_db),
) -> List[BadgeResponse]:
    """List all available badge definitions."""
    return progress_service.list_badges(db)


@router.get("/badges/user", response_model=List[UserBadgeResponse])
def get_user_badges(
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> List[UserBadgeResponse]:
    """List badges earned by the current user."""
    raw = progress_service.get_user_badges(db, current_user.sub)
    return [UserBadgeResponse(**item) for item in raw]
