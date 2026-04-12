"""Progress service - business logic for progress tracking and badge awarding."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import Badge, UserBadge
from app.repositories import badge_repo  # type: ignore[attr-defined]
from app.repositories import progress_repo
from app.schemas.progress_schemas import (
    BadgeResponse,
    CourseProgressResponse,
    LessonProgressResponse,
    ProgressUpdateResult,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_lesson_response(record) -> LessonProgressResponse:
    last_activity = record.last_activity
    if hasattr(last_activity, "isoformat"):
        last_activity = last_activity.isoformat()
    return LessonProgressResponse(
        lesson_id=record.lesson_id,
        status=record.status,
        last_activity=str(last_activity),
        last_score=record.last_score,
    )


def _to_course_response(
    record, lesson_count: int, completed_count: int
) -> CourseProgressResponse:
    updated_at = record.updated_at
    if hasattr(updated_at, "isoformat"):
        updated_at = updated_at.isoformat()
    return CourseProgressResponse(
        course_id=record.course_id,
        percent=record.percent,
        status=record.status,
        lesson_count=lesson_count,
        completed_count=completed_count,
        updated_at=str(updated_at),
    )


def _to_badge_response(badge: Badge) -> BadgeResponse:
    return BadgeResponse(
        id=badge.id,
        slug=badge.slug,
        name=badge.name,
        description=badge.description,
        icon=badge.icon,
    )


def _try_award(
    db: Session,
    user_id: str,
    slug: str,
    context_id: Optional[str],
) -> Optional[BadgeResponse]:
    """Award badge with slug to user if not already earned. Returns BadgeResponse or None."""
    badge = badge_repo.get_badge_by_slug(db, slug)
    if badge is None:
        return None
    if badge_repo.has_user_badge(db, user_id, badge.id):
        return None
    badge_repo.award_badge(db, user_id, badge.id, context_id)
    return _to_badge_response(badge)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_lesson_progress(
    db: Session,
    user_id: str,
    lesson_id: str,
    course_id: str,
    status: str,
    score: Optional[int] = None,
) -> ProgressUpdateResult:
    """Update lesson progress and recalculate course progress.

    Awards badges when:
    - A lesson is completed for the first time (lesson_complete badge).
    - All lessons in the course are completed (course_complete badge).
    """
    # 1. Upsert lesson progress
    lesson_record = progress_repo.upsert_lesson_progress(
        db, user_id, lesson_id, status, score
    )

    # 2. Recalculate course progress
    lesson_count = progress_repo.count_lessons_in_course(db, course_id)
    completed_count = progress_repo.count_completed_lessons(db, user_id, course_id)

    if lesson_count > 0:
        percent = int((completed_count / lesson_count) * 100)
    else:
        percent = 0

    started_count = progress_repo.count_started_lessons(db, user_id, course_id)
    course_status = "completed" if percent == 100 else (
        "in_progress" if started_count > 0 else "not_started"
    )
    course_record = progress_repo.upsert_course_progress(
        db, user_id, course_id, percent, course_status
    )

    # 3. Badge awarding
    new_badges: List[BadgeResponse] = []

    if status == "completed":
        awarded = _try_award(db, user_id, "lesson_complete", lesson_id)
        if awarded:
            new_badges.append(awarded)

    if percent == 100:
        awarded = _try_award(db, user_id, "course_complete", course_id)
        if awarded:
            new_badges.append(awarded)

    return ProgressUpdateResult(
        lesson_progress=_to_lesson_response(lesson_record),
        course_progress=_to_course_response(course_record, lesson_count, completed_count),
        new_badges=new_badges,
    )


def get_course_progress(
    db: Session, user_id: str, course_id: str
) -> CourseProgressResponse:
    """Return current course progress, creating a default record if none exists."""
    lesson_count = progress_repo.count_lessons_in_course(db, course_id)
    completed_count = progress_repo.count_completed_lessons(db, user_id, course_id)

    record = progress_repo.get_course_progress(db, user_id, course_id)
    if record is None:
        record = progress_repo.upsert_course_progress(
            db, user_id, course_id, percent=0, status="not_started"
        )

    return _to_course_response(record, lesson_count, completed_count)


def list_badges(db: Session) -> List[BadgeResponse]:
    return [_to_badge_response(b) for b in badge_repo.get_all_badges(db)]


def get_user_badges(db: Session, user_id: str) -> List[dict]:
    user_badges: List[UserBadge] = badge_repo.get_user_badges(db, user_id)
    result = []
    for ub in user_badges:
        earned_at = ub.earned_at
        if hasattr(earned_at, "isoformat"):
            earned_at = earned_at.isoformat()
        result.append({
            "id": ub.id,
            "badge": _to_badge_response(ub.badge),
            "earned_at": str(earned_at),
            "context_id": ub.context_id,
        })
    return result
