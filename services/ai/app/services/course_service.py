"""Course service - business logic for course and lesson retrieval."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import Course, Lesson
from app.repositories import course_repo


def list_courses(db: Session, skip: int = 0, limit: int = 100) -> List[Course]:
    return course_repo.get_all_courses(db, skip=skip, limit=limit)


def get_course(db: Session, course_id: str) -> Optional[Course]:
    return course_repo.get_course_by_id(db, course_id)


def get_course_lessons(db: Session, course_id: str) -> List[Lesson]:
    return course_repo.get_lessons_by_course_id(db, course_id)


def get_lesson(db: Session, lesson_id: str) -> Optional[Lesson]:
    return course_repo.get_lesson_by_id(db, lesson_id)
