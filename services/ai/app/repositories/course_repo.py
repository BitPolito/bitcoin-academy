"""Course repository - data access for course aggregate."""
courses = [
    {"id": 1, "title": "Python Basics", "description": "Learn Python from scratch"},
    {"id": 2, "title": "FastAPI Advanced", "description": "Deep dive into FastAPI"}
]

lessons = [
    {"id": 1, "course_id": 1, "title": "Variables and Types", "content": "Intro to types"},
    {"id": 2, "course_id": 1, "title": "Functions", "content": "How to define functions"},
    {"id": 3, "course_id": 2, "title": "Routing", "content": "Learn how routing works"},
]

def get_all_courses():
    return courses

def get_course_by_id(course_id: int):
    return next((c for c in courses if c["id"] == course_id), None)

def get_lessons_by_course_id(course_id: int):
    return [l for l in lessons if l["course_id"] == course_id]

def get_lesson_by_id(lesson_id: int):
    return next((l for l in lessons if l["id"] == lesson_id), None)