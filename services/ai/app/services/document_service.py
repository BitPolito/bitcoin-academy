"""Document service - business logic for document upload, status, and preview."""
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import ChunkParent, CourseDocument, DocumentProcessingStage, DocumentStatus
from app.repositories import document_repo
from app.schemas.pagination import encode_cursor

logger = logging.getLogger(__name__)


def list_documents(db: Session, course_id: str) -> List[CourseDocument]:
    return document_repo.list_by_course(db, course_id)


def list_documents_page(
    db: Session,
    course_id: str,
    *,
    after: tuple[str, str] | None,
    limit: int,
) -> tuple[List[CourseDocument], str | None]:
    documents, has_more = document_repo.list_page_by_course(
        db, course_id, after=after, limit=limit
    )
    next_cursor = (
        encode_cursor(documents[-1].created_at, documents[-1].id)
        if has_more and documents
        else None
    )
    return documents, next_cursor


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
    created = document_repo.create(db, doc)
    from app.services.outline_staleness_service import mark_new_document
    mark_new_document(db, course_id, filename)
    db.commit()
    return created


def reset_status(db: Session, document_id: str) -> Optional[CourseDocument]:
    """Reset a failed document to pending so the pipeline can retry it."""
    doc = document_repo.get_by_id(db, document_id)
    if doc is None:
        return None
    from app.services.outline_staleness_service import mark_document_changed
    mark_document_changed(db, document_id, f'Source "{doc.filename}" is being reprocessed.')
    doc.status = DocumentStatus.PROCESSING
    doc.processing_stage = DocumentProcessingStage.QUEUED
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    return doc


def _qvac_delete_workspace_chunks(course_id: str, doc_id: str) -> None:
    """Best-effort request to drop this document's vectors from QVAC.

    The QVAC Node service (external, not in this repo) is not confirmed to
    expose a delete-by-document endpoint — unlike /ingest and /query which are
    used elsewhere in this codebase. This call degrades silently (logged at
    debug) if the endpoint doesn't exist or QVAC is unreachable, matching the
    resilience pattern already used for QVAC calls throughout the codebase.
    Stale vectors left behind are a known limitation until the endpoint
    contract is confirmed — see docs/feature-status.md §3.
    """
    import os  # noqa: PLC0415
    import httpx  # noqa: PLC0415

    qvac_url = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
    try:
        with httpx.Client(timeout=10.0) as client:
            client.delete(f"{qvac_url}/documents/{doc_id}", params={"workspace": course_id})
    except httpx.HTTPError as exc:
        logger.debug("QVAC vector cleanup skipped for doc %s: %s", doc_id, exc)


def delete_document(db: Session, document_id: str, commit: bool = True) -> bool:
    """Delete a document: DB row, its chunk_parent rows, the uploaded file,
    and (best-effort) its QVAC vectors.

    commit=False lets a caller (course_service.delete_course) fold several
    documents' deletions into one outer transaction instead of committing
    each document individually — a mid-cascade failure then rolls back
    everything instead of leaving some documents deleted and others not.
    """
    doc = document_repo.get_by_id(db, document_id)
    if doc is None:
        return False

    from app.services.outline_staleness_service import mark_document_changed
    mark_document_changed(db, document_id, f'Source "{doc.filename}" was deleted.')

    db.query(ChunkParent).filter(ChunkParent.doc_id == document_id).delete()

    from app.workers.pipeline import UPLOADS_DIR  # noqa: PLC0415
    upload_dir = UPLOADS_DIR / doc.course_id
    if upload_dir.is_dir():
        for f in upload_dir.glob(f"{document_id}_*"):
            try:
                f.unlink()
            except OSError as exc:
                logger.warning("Could not remove uploaded file %s: %s", f, exc)

    _qvac_delete_workspace_chunks(doc.course_id, document_id)

    document_repo.delete(db, doc, commit=commit)
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
