"""Progress repository - data access for progress tracking."""
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Chapter, Lesson, UserCourseProgress, UserLessonProgress


def get_lesson_progress(
    db: Session, user_id: str, lesson_id: str
) -> Optional[UserLessonProgress]:
    return (
        db.query(UserLessonProgress)
        .filter_by(user_id=user_id, lesson_id=lesson_id)
        .first()
    )


def upsert_lesson_progress(
    db: Session,
    user_id: str,
    lesson_id: str,
    status: str,
    score: Optional[int] = None,
) -> UserLessonProgress:
    record = get_lesson_progress(db, user_id, lesson_id)
    now = datetime.now()
    if record is None:
        record = UserLessonProgress(
            user_id=user_id,
            lesson_id=lesson_id,
            status=status,
            last_activity=now,
            last_score=score,
        )
        db.add(record)
    else:
        record.status = status
        record.last_activity = now
        if score is not None:
            record.last_score = score
    db.commit()
    db.refresh(record)
    return record


def get_course_progress(
    db: Session, user_id: str, course_id: str
) -> Optional[UserCourseProgress]:
    return (
        db.query(UserCourseProgress)
        .filter_by(user_id=user_id, course_id=course_id)
        .first()
    )


def upsert_course_progress(
    db: Session,
    user_id: str,
    course_id: str,
    percent: int,
    status: str,
) -> UserCourseProgress:
    record = get_course_progress(db, user_id, course_id)
    now = datetime.now()
    if record is None:
        record = UserCourseProgress(
            user_id=user_id,
            course_id=course_id,
            percent=percent,
            status=status,
            updated_at=now,
        )
        db.add(record)
    else:
        record.percent = percent
        record.status = status
        record.updated_at = now
    db.commit()
    db.refresh(record)
    return record


def count_lessons_in_course(db: Session, course_id: str) -> int:
    return (
        db.query(func.count(Lesson.id))
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(Chapter.course_id == course_id)
        .scalar()
        or 0
    )


def count_started_lessons(db: Session, user_id: str, course_id: str) -> int:
    """Count lessons that have any progress record (in_progress or completed)."""
    return (
        db.query(func.count(UserLessonProgress.lesson_id))
        .join(Lesson, UserLessonProgress.lesson_id == Lesson.id)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(
            Chapter.course_id == course_id,
            UserLessonProgress.user_id == user_id,
        )
        .scalar()
        or 0
    )


def count_completed_lessons(db: Session, user_id: str, course_id: str) -> int:
    return (
        db.query(func.count(UserLessonProgress.lesson_id))
        .join(Lesson, UserLessonProgress.lesson_id == Lesson.id)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(
            Chapter.course_id == course_id,
            UserLessonProgress.user_id == user_id,
            UserLessonProgress.status == "completed",
        )
        .scalar()
        or 0
    )


def get_completed_lesson_ids(db: Session, user_id: str, course_id: str) -> list[str]:
    rows = (
        db.query(UserLessonProgress.lesson_id)
        .join(Lesson, UserLessonProgress.lesson_id == Lesson.id)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(
            Chapter.course_id == course_id,
            UserLessonProgress.user_id == user_id,
            UserLessonProgress.status == "completed",
        )
        .all()
    )
    return [row[0] for row in rows]
