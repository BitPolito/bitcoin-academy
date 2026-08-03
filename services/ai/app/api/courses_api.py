"""Courses API controller - HTTP + error mapping with input validation."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import UserRole
from app.middleware.auth import CurrentUser, get_current_user
from app.services import course_service
from app.schemas.course_schemas import CourseSchema, LessonSchema
from app.core.errors import NotFoundError, ValidationError_

router = APIRouter(prefix="/api", tags=["Courses"])


class CreateCourseBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class UpdateCourseBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class ReindexResponse(BaseModel):
    enqueued: int
    skipped: int


@router.post("/courses", response_model=CourseSchema, status_code=201)
def create_course(
    body: CreateCourseBody,
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new course workspace."""
    return course_service.create_course(db, title=body.title, description=body.description)


@router.get("/courses", response_model=List[CourseSchema])
def get_courses(
    skip: int = Query(default=0, ge=0, le=1000, description="Number of courses to skip"),
    limit: int = Query(default=100, ge=1, le=100, description="Maximum number of courses to return"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    """Get a list of all available courses."""
    return course_service.list_courses(db, skip=skip, limit=limit)


@router.get("/courses/{course_id}", response_model=CourseSchema)
def get_course(
    course_id: str = Path(..., min_length=1, max_length=36, description="Course UUID"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    """Get details of a specific course by UUID."""
    try:
        UUID(course_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid course ID format. Expected UUID.",
            details={"course_id": course_id},
        )

    result = course_service.get_course(db, course_id)
    if result is None:
        raise NotFoundError(resource="Course", identifier=course_id)
    return result


@router.patch("/courses/{course_id}", response_model=CourseSchema)
def update_course(
    body: UpdateCourseBody,
    course_id: str = Path(..., min_length=1, max_length=36, description="Course UUID"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    """Update course title and description."""
    try:
        UUID(course_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid course ID format. Expected UUID.",
            details={"course_id": course_id},
        )

    result = course_service.update_course(
        db, course_id=course_id, title=body.title, description=body.description
    )
    if result is None:
        raise NotFoundError(resource="Course", identifier=course_id)
    return result


@router.delete("/courses/{course_id}")
def delete_course(
    course_id: str = Path(..., min_length=1, max_length=36, description="Course UUID"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(CurrentUser(roles=[UserRole.ADMIN, UserRole.INSTRUCTOR])),
):
    """Delete a course: documents (+ files, QVAC vectors, chunks), chapters,
    lessons, quizzes, attempts, generation runs, and progress. Certificates
    are revoked, not deleted, so verification stays honest. Instructor/admin only."""
    try:
        UUID(course_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid course ID format. Expected UUID.",
            details={"course_id": course_id},
        )

    counts = course_service.delete_course(db, course_id)
    if counts is None:
        raise NotFoundError(resource="Course", identifier=course_id)
    return {"message": "Course deleted", "counts": counts}


@router.get("/courses/{course_id}/lessons", response_model=List[LessonSchema])
def get_course_lessons(
    course_id: str = Path(..., min_length=1, max_length=36, description="Course UUID"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    """Get all lessons for a specific course."""
    try:
        UUID(course_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid course ID format. Expected UUID.",
            details={"course_id": course_id},
        )

    course = course_service.get_course(db, course_id)
    if course is None:
        raise NotFoundError(resource="Course", identifier=course_id)

    return course_service.get_course_lessons(db, course_id)


@router.post("/courses/{course_id}/reindex", response_model=ReindexResponse)
async def reindex_course(
    request: Request,
    background_tasks: BackgroundTasks,
    course_id: str = Path(..., min_length=1, max_length=36, description="Course UUID"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
) -> ReindexResponse:
    """Re-ingest all documents in a course (full parse → chunk → BM25 → QVAC)."""
    from app.services import document_service
    from app.workers import pipeline
    from app.workers.pipeline import UPLOADS_DIR

    try:
        UUID(course_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid course ID format. Expected UUID.",
            details={"course_id": course_id},
        )

    documents = document_service.list_documents(db, course_id)
    arq_pool = getattr(request.app.state, "arq_pool", None)
    enqueued = 0
    skipped = 0

    for doc in documents:
        file_path = UPLOADS_DIR / course_id / f"{doc.id}_{doc.filename}"
        if not file_path.exists():
            skipped += 1
            continue
        document_service.reset_status(db, doc.id)
        if arq_pool is not None:
            await arq_pool.enqueue_job(
                "ingest_document",
                document_id=doc.id,
                course_id=course_id,
                filename=doc.filename,
                file_path=str(file_path),
                material_type=doc.document_type,
            )
        else:
            background_tasks.add_task(
                pipeline.run,
                document_id=doc.id,
                course_id=course_id,
                filename=doc.filename,
                file_path=str(file_path),
                material_type=doc.document_type,
            )
        enqueued += 1

    return ReindexResponse(enqueued=enqueued, skipped=skipped)


@router.get("/lessons/{lesson_id}", response_model=LessonSchema)
def get_lesson(
    lesson_id: str = Path(..., min_length=1, max_length=36, description="Lesson UUID"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    """Get details of a specific lesson by UUID."""
    try:
        UUID(lesson_id)
    except ValueError:
        raise ValidationError_(
            message="Invalid lesson ID format. Expected UUID.",
            details={"lesson_id": lesson_id},
        )

    result = course_service.get_lesson(db, lesson_id)
    if result is None:
        raise NotFoundError(resource="Lesson", identifier=lesson_id)
    return result
