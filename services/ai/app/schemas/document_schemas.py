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
    chunk_count: Optional[int] = None
    sections: Optional[List[str]] = None
    sample_chunks: Optional[List[Dict[str, Any]]] = None

    class Config:
        orm_mode = True


class SectionNode(BaseModel):
    """One heading in the document's section tree (course builder source)."""
    title: str
    level: int
    page_start: int
    page_end: int
    parent_chunk_ids: List[str]
    children: List["SectionNode"] = []


class DocumentStructure(BaseModel):
    document_id: str
    # "ingest" = heading hierarchy extracted at ingest;
    # "rebuilt" = flat tree reconstructed from chunk_parent (legacy docs);
    # "unavailable" = document not READY or no parents indexed.
    source: str
    tree: Optional[List[SectionNode]] = None
