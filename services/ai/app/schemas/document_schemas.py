"""Pydantic schemas for document DTOs."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DocumentListItem(BaseModel):
    id: str
    course_id: str
    filename: str
    mime_type: Optional[str] = None
    size: int
    status: str
    processing_stage: str
    error_message: Optional[str] = None
    document_type: str = "lecture"
    created_at: str
    updated_at: str

    class Config:
        orm_mode = True


class DocumentStatusResponse(BaseModel):
    id: str
    status: str
    processing_stage: str
    error_message: Optional[str] = None


class DocumentDetail(BaseModel):
    id: str
    course_id: str
    filename: str
    mime_type: Optional[str] = None
    size: int
    status: str
    processing_stage: str
    error_message: Optional[str] = None
    document_type: str = "lecture"
    parser_used: Optional[str] = None
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    indexing_status: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        orm_mode = True


class DocumentPreview(BaseModel):
    id: str
    filename: str
    extracted_text_preview: Optional[str] = None
    page_count: Optional[int] = None
    sections: Optional[List[str]] = None
    sample_chunks: Optional[List[Dict[str, Any]]] = None

    class Config:
        orm_mode = True
