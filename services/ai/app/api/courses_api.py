"""Courses API controller - HTTP + error mapping with input validation."""
from fastapi import APIRouter, Path, Query
from typing import List, Optional

from app.services import course_service
from app.schemas.course_schemas import CourseSchema, LessonSchema
from app.core.errors import NotFoundError, ValidationError_

router = APIRouter(prefix="/api", tags=["Courses"])


@router.get("/courses", response_model=List[CourseSchema])
def get_courses(
    skip: int = Query(
        default=0,
        ge=0,
        le=1000,
        description="Number of courses to skip"
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of courses to return"
    ),
) -> List[CourseSchema]:
    """
    Get a list of all available courses.

    - **skip**: Number of courses to skip (pagination)
    - **limit**: Maximum number of courses to return (max 100)
    """
    return course_service.list_courses()


@router.get("/courses/{course_id}", response_model=CourseSchema)
def get_course(
    course_id: int = Path(
        ...,
        gt=0,
        le=2147483647,  # Max int32 to prevent overflow
        description="The ID of the course to retrieve"
    ),
) -> CourseSchema:
    """
    Get details of a specific course by ID.

    - **course_id**: Unique course identifier (must be positive integer)
    """
    result = course_service.get_course(course_id)
    if result is None:
        raise NotFoundError(resource="Course", identifier=str(course_id))
    return result


@router.get("/courses/{course_id}/lessons", response_model=List[LessonSchema])
def get_course_lessons(
    course_id: int = Path(
        ...,
        gt=0,
        le=2147483647,
        description="The ID of the course to get lessons for"
    ),
) -> List[LessonSchema]:
    """
    Get all lessons for a specific course.

    - **course_id**: Unique course identifier (must be positive integer)
    """
    # First verify the course exists
    course = course_service.get_course(course_id)
    if course is None:
        raise NotFoundError(resource="Course", identifier=str(course_id))

    return course_service.get_course_lessons(course_id)


@router.get("/lessons/{lesson_id}", response_model=LessonSchema)
def get_lesson(
    lesson_id: int = Path(
        ...,
        gt=0,
        le=2147483647,
        description="The ID of the lesson to retrieve"
    ),
) -> LessonSchema:
    """
    Get details of a specific lesson by ID.

    - **lesson_id**: Unique lesson identifier (must be positive integer)
    """
    result = course_service.get_lesson(lesson_id)
    if result is None:
        raise NotFoundError(resource="Lesson", identifier=str(lesson_id))
    return result
