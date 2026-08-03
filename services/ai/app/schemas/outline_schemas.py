"""Pydantic schemas for outline generation endpoints."""
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GenerationRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    status: str
    stage: Optional[str] = None
    error_message: Optional[str] = None
    prompt_version: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: str

    @property
    def doc_ids(self) -> List[str]:
        try:
            return json.loads(self.doc_ids_json) if hasattr(self, "doc_ids_json") else []
        except (json.JSONDecodeError, AttributeError):
            return []


class LessonDraftSchema(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    order_index: int
    source_refs: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=False)


class ChapterDraftSchema(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    order_index: int
    lessons: List[LessonDraftSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=False)


class OutlineResponse(BaseModel):
    course_id: str
    run_id: Optional[str] = None
    chapters: List[ChapterDraftSchema] = Field(default_factory=list)


# ---- Request bodies ----

class GenerateOutlineBody(BaseModel):
    doc_ids: Optional[List[str]] = Field(
        default=None,
        description="Document IDs to include; defaults to all READY docs in the course",
    )
    options: Optional[Dict[str, Any]] = Field(default=None)


class LessonPatch(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    order_index: Optional[int] = None
    delete: bool = False


class ChapterPatch(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    order_index: Optional[int] = None
    delete: bool = False
    lessons: List[LessonPatch] = Field(default_factory=list)


class PatchOutlineBody(BaseModel):
    chapters: List[ChapterPatch] = Field(default_factory=list)
