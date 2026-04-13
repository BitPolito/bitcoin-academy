"""Courses API controller - HTTP + error mapping with input validation."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import course_service
from app.schemas.course_schemas import CourseSchema, LessonSchema
from app.core.errors import NotFoundError, ValidationError_

router = APIRouter(prefix="/api", tags=["Courses"])


@router.get("/courses", response_model=List[CourseSchema])
def get_courses(
    skip: int = Query(default=0, ge=0, le=1000, description="Number of courses to skip"),
    limit: int = Query(default=100, ge=1, le=100, description="Maximum number of courses to return"),
    db: Session = Depends(get_db),
) -> List[CourseSchema]:
    """Get a list of all available courses."""
    return course_service.list_courses(db, skip=skip, limit=limit)


@router.get("/courses/{course_id}", response_model=CourseSchema)
def get_course(
    course_id: str = Path(..., min_length=1, max_length=36, description="Course UUID"),
    db: Session = Depends(get_db),
) -> CourseSchema:
    """Get details of a specific course by UUID."""
    try:
        UUID(course_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid course ID format. Expected UUID.",
            details={"course_id": course_id},
        )

    result = course_service.get_course(db, course_id)
    if result is None:
        raise NotFoundError(resource="Course", identifier=course_id)
    return result


@router.get("/courses/{course_id}/lessons", response_model=List[LessonSchema])
def get_course_lessons(
    course_id: str = Path(..., min_length=1, max_length=36, description="Course UUID"),
    db: Session = Depends(get_db),
) -> List[LessonSchema]:
    """Get all lessons for a specific course."""
    try:
        UUID(course_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid course ID format. Expected UUID.",
            details={"course_id": course_id},
        )

    course = course_service.get_course(db, course_id)
    if course is None:
        raise NotFoundError(resource="Course", identifier=course_id)

    return course_service.get_course_lessons(db, course_id)


@router.get("/lessons/{lesson_id}", response_model=LessonSchema)
def get_lesson(
    lesson_id: str = Path(..., min_length=1, max_length=36, description="Lesson UUID"),
    db: Session = Depends(get_db),
) -> LessonSchema:
    """Get details of a specific lesson by UUID."""
    try:
        UUID(lesson_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid lesson ID format. Expected UUID.",
            details={"lesson_id": lesson_id},
        )

    result = course_service.get_lesson(db, lesson_id)
    if result is None:
        raise NotFoundError(resource="Lesson", identifier=lesson_id)
    return result
