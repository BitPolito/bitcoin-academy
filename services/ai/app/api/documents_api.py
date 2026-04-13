"""Documents API controller - upload, list, status, detail, preview."""
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, Path, UploadFile, File
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import document_service
from app.workers import pipeline
from app.schemas.document_schemas import (
    DocumentDetail,
    DocumentListItem,
    DocumentPreview,
    DocumentStatusResponse,
)
from app.core.errors import NotFoundError

router = APIRouter(prefix="/api", tags=["Documents"])


@router.get(
    "/courses/{course_id}/documents",
    response_model=List[DocumentListItem],
)
def list_documents(
    course_id: str = Path(..., description="Course ID"),
    db: Session = Depends(get_db),
) -> List[DocumentListItem]:
    return document_service.list_documents(db, course_id)


@router.post(
    "/courses/{course_id}/documents",
    response_model=DocumentListItem,
    status_code=201,
)
def upload_document(
    course_id: str = Path(..., description="Course ID"),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
) -> DocumentListItem:
    content = file.file.read()
    filename = file.filename or "unknown"
    doc = document_service.create_document(
        db,
        course_id=course_id,
        filename=filename,
        size=len(content),
        mime_type=file.content_type,
    )
    background_tasks.add_task(pipeline.run, doc.id, course_id, filename)
    return doc


@router.get(
    "/documents/{document_id}/status",
    response_model=DocumentStatusResponse,
)
def get_document_status(
    document_id: str = Path(..., description="Document ID"),
    db: Session = Depends(get_db),
) -> DocumentStatusResponse:
    doc = document_service.get_document(db, document_id)
    if doc is None:
        raise NotFoundError(resource="Document", identifier=document_id)
    return doc


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
)
def get_document_detail(
    document_id: str = Path(..., description="Document ID"),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    doc = document_service.get_document(db, document_id)
    if doc is None:
        raise NotFoundError(resource="Document", identifier=document_id)
    return doc


@router.get(
    "/documents/{document_id}/preview",
    response_model=DocumentPreview,
)
def get_document_preview(
    document_id: str = Path(..., description="Document ID"),
    db: Session = Depends(get_db),
) -> DocumentPreview:
    preview = document_service.get_preview(db, document_id)
    if preview is None:
        raise NotFoundError(resource="Document", identifier=document_id)
    return preview


@router.delete(
    "/documents/{document_id}",
    status_code=200,
)
def delete_document(
    document_id: str = Path(..., description="Document ID"),
    db: Session = Depends(get_db),
):
    deleted = document_service.delete_document(db, document_id)
    if not deleted:
        raise NotFoundError(resource="Document", identifier=document_id)
    return {"message": "Document deleted"}
