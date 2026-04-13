"""Pydantic schemas for course DTOs."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class LessonSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    content: Optional[str] = None


class CourseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None


class CourseWithLessonsSchema(CourseSchema):
    lessons: List[LessonSchema] = []
