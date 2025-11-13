"""Pydantic schemas for course DTOs."""
from pydantic import BaseModel
from typing import List, Optional

class LessonSchema(BaseModel):
    id: int
    title: str
    content: Optional[str] = None

    class Config:
        orm_mode = True


class CourseSchema(BaseModel):
    id: int
    title: str
    description: Optional[str] = None

    class Config:
        orm_mode = True


class CourseWithLessonsSchema(CourseSchema):
    lessons: List[LessonSchema] = []