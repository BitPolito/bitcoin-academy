"""Pydantic schemas for progress and badge DTOs."""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class LessonProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class UpdateLessonProgressRequest(BaseModel):
    lesson_id: str = Field(min_length=1, max_length=36)
    course_id: str = Field(min_length=1, max_length=36)
    status: LessonProgressStatus
    score: Optional[int] = Field(None, ge=0, le=100)


class LessonProgressResponse(BaseModel):
    lesson_id: str
    status: str
    last_activity: str
    last_score: Optional[int] = None

    class Config:
        from_attributes = True


class CourseProgressResponse(BaseModel):
    course_id: str
    percent: int
    status: str
    lesson_count: int
    completed_count: int
    updated_at: str
    completed_lesson_ids: List[str] = []

    class Config:
        from_attributes = True


class BadgeResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    icon: str

    class Config:
        from_attributes = True


class UserBadgeResponse(BaseModel):
    id: str
    badge: BadgeResponse
    earned_at: str
    context_id: Optional[str] = None

    class Config:
        from_attributes = True


class ProgressUpdateResult(BaseModel):
    lesson_progress: LessonProgressResponse
    course_progress: CourseProgressResponse
    new_badges: List[BadgeResponse] = []
