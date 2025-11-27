"""Courses API controller - HTTP + error mapping."""
from fastapi import APIRouter
from typing import List
from app.services import course_service
from app.schemas.course_schemas import CourseSchema, LessonSchema

router = APIRouter(prefix="/api", tags=["Courses"])


@router.get("/courses", response_model=List[CourseSchema])
def get_courses():
    return course_service.list_courses()


@router.get("/courses/{course_id}", response_model=CourseSchema)
def get_course(course_id: int):
    return course_service.get_course(course_id)


@router.get("/courses/{course_id}/lessons", response_model=List[LessonSchema])
def get_course_lessons(course_id: int):
    return course_service.get_course_lessons(course_id)


@router.get("/lessons/{lesson_id}", response_model=LessonSchema)
def get_lesson(lesson_id: int):
    return course_service.get_lesson(lesson_id)
