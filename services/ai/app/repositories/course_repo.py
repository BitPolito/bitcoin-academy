"""Course repository - data access for course aggregate."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import Chapter, Course, Lesson


def get_all_courses(db: Session, skip: int = 0, limit: int = 100) -> List[Course]:
    return db.query(Course).filter(Course.is_active == True).offset(skip).limit(limit).all()


def get_course_by_id(db: Session, course_id: str) -> Optional[Course]:
    return db.query(Course).filter(Course.id == course_id, Course.is_active == True).first()


def get_lessons_by_course_id(db: Session, course_id: str) -> List[Lesson]:
    return (
        db.query(Lesson)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(Chapter.course_id == course_id)
        .order_by(Chapter.order_index, Lesson.order_index)
        .all()
    )


def get_lesson_by_id(db: Session, lesson_id: str) -> Optional[Lesson]:
    return db.query(Lesson).filter(Lesson.id == lesson_id).first()
