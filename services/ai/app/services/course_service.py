"""Course service - business logic for create/update course, structure checks."""
from repositories import course_repo
from fastapi import HTTPException

def list_courses():
    return course_repo.get_all_courses()

def get_course(course_id: int):
    course = course_repo.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

def get_course_lessons(course_id: int):
    course = course_repo.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course_repo.get_lessons_by_course_id(course_id)

def get_lesson(lesson_id: int):
    lesson = course_repo.get_lesson_by_id(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson