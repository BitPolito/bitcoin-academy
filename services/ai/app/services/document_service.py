"""Document service - business logic for document upload, status, and preview."""
import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import ChunkParent, CourseDocument, DocumentProcessingStage, DocumentStatus
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
    document_type: str = "lecture",
) -> CourseDocument:
    doc = CourseDocument(
        id=str(uuid.uuid4()),
        course_id=course_id,
        filename=filename,
        mime_type=mime_type,
        size=size,
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.QUEUED,
        document_type=document_type,
    )
    return document_repo.create(db, doc)


def reset_status(db: Session, document_id: str) -> Optional[CourseDocument]:
    """Reset a failed document to pending so the pipeline can retry it."""
    doc = document_repo.get_by_id(db, document_id)
    if doc is None:
        return None
    doc.status = DocumentStatus.PROCESSING
    doc.processing_stage = DocumentProcessingStage.QUEUED
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    return doc


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
        "chunk_count": doc.chunk_count,
        "sections": sections,
        "sample_chunks": sample_chunks,
    }


def get_section_tree(db: Session, document_id: str) -> Optional[Dict[str, Any]]:
    """Return the document's heading tree, rebuilding it for legacy documents.

    Documents ingested before the section-tree stage have no
    section_tree_json and their source file may be gone (the pipeline
    deletes it), so a full re-parse is impossible. In that case a flat
    level-1 tree is rebuilt on the fly from the chunk_parent rows (which
    preserve section title and page per parent) and returned with
    source="rebuilt" — not persisted, so the flag stays honest.
    Re-ingesting via POST /courses/{id}/reindex produces the full heading
    hierarchy (source="ingest").
    """
    doc = document_repo.get_by_id(db, document_id)
    if doc is None:
        return None

    if doc.section_tree_json:
        try:
            return {"tree": json.loads(doc.section_tree_json), "source": "ingest"}
        except json.JSONDecodeError:
            pass  # corrupt blob — fall through to rebuild

    if doc.status != DocumentStatus.READY:
        return {"tree": None, "source": "unavailable"}

    from app.workers.pipeline import build_section_events_from_parents, build_section_tree

    parent_rows = (
        db.query(ChunkParent)
        .filter(ChunkParent.doc_id == document_id)
        .order_by(ChunkParent.id)
        .all()
    )
    if not parent_rows:
        return {"tree": None, "source": "unavailable"}

    tree = build_section_tree(build_section_events_from_parents(parent_rows))
    return {"tree": tree, "source": "rebuilt"}
