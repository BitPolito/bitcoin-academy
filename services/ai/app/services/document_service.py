"""Document service - business logic for document upload, status, and preview."""
import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus
from app.repositories import document_repo


def list_documents(db: Session, course_id: str) -> List[CourseDocument]:
    return document_repo.list_by_course(db, course_id)


def get_document(db: Session, document_id: str) -> Optional[CourseDocument]:
    return document_repo.get_by_id(db, document_id)


def create_document(
    db: Session,
    course_id: str,
    filename: str,
    size: int,
    mime_type: Optional[str] = None,
) -> CourseDocument:
    doc = CourseDocument(
        id=str(uuid.uuid4()),
        course_id=course_id,
        filename=filename,
        mime_type=mime_type,
        size=size,
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.QUEUED,
    )
    return document_repo.create(db, doc)


def delete_document(db: Session, document_id: str) -> bool:
    doc = document_repo.get_by_id(db, document_id)
    if doc is None:
        return False
    document_repo.delete(db, doc)
    return True


def get_preview(db: Session, document_id: str) -> Optional[Dict[str, Any]]:
    doc = document_repo.get_by_id(db, document_id)
    if doc is None:
        return None

    sections = None
    if doc.sections_json:
        try:
            sections = json.loads(doc.sections_json)
        except json.JSONDecodeError:
            sections = None

    sample_chunks = None
    if doc.sample_chunks_json:
        try:
            sample_chunks = json.loads(doc.sample_chunks_json)
        except json.JSONDecodeError:
            sample_chunks = None

    return {
        "id": doc.id,
        "filename": doc.filename,
        "extracted_text_preview": doc.extracted_text_preview,
        "page_count": doc.page_count,
        "sections": sections,
        "sample_chunks": sample_chunks,
    }
