"""Outline API — course builder phase 2.

Endpoints:
  POST   /courses/{id}/outline/generate   → enqueue map-reduce job, return run_id
  GET    /courses/{id}/outline            → draft chapters/lessons
  PATCH  /courses/{id}/outline            → rename / reorder / delete draft items
  GET    /generation-runs/{run_id}        → job status + stage
"""
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError_
from app.db.models import (
    Chapter,
    DocumentStatus,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
    UserRole,
)
from app.db.session import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.schemas.outline_schemas import (
    ChapterDraftSchema,
    GenerateOutlineBody,
    GenerationRunSchema,
    LessonDraftSchema,
    OutlineActionBody,
    OutlineResponse,
    PatchOutlineBody,
)
from app.services import course_service

router = APIRouter(prefix="/api", tags=["Outline"])

_require_reviewer = CurrentUser(roles=[UserRole.ADMIN, UserRole.INSTRUCTOR])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chapter_to_schema(chapter: Chapter) -> ChapterDraftSchema:
    lessons = [
        LessonDraftSchema(
            id=ls.id,
            title=ls.title,
            description=ls.description,
            status=ls.status,
            order_index=ls.order_index,
            source_refs=json.loads(ls.source_refs_json) if ls.source_refs_json else [],
            is_human_modified=ls.is_human_modified,
            human_modified_at=ls.human_modified_at,
        )
        for ls in sorted(chapter.lessons, key=lambda x: x.order_index)
    ]
    return ChapterDraftSchema(
        id=chapter.id,
        title=chapter.title,
        description=chapter.description,
        status=chapter.status,
        order_index=chapter.order_index,
        lessons=lessons,
        is_human_modified=chapter.is_human_modified,
        human_modified_at=chapter.human_modified_at,
    )


def _latest_run_id(course_id: str, db: Session) -> str | None:
    run = (
        db.query(GenerationRun)
        .filter(GenerationRun.course_id == course_id)
        .order_by(GenerationRun.created_at.desc())
        .first()
    )
    return run.id if run else None


async def _run_outline_bg(course_id: str, doc_ids: list, run_id: str) -> None:
    """Async background task (fallback when ARQ is unavailable)."""
    from app.db.session import get_db_context
    from app.services import outline_service

    with get_db_context() as db:
        await outline_service.generate_outline(
            course_id=course_id,
            doc_ids=doc_ids,
            db=db,
            run_id=run_id,
        )


# ---------------------------------------------------------------------------
# POST /courses/{course_id}/outline/generate
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/outline/generate",
    status_code=202,
    summary="Start outline generation job (map-reduce over document sections)",
)
async def generate_outline(
    request: Request,
    background_tasks: BackgroundTasks,
    body: GenerateOutlineBody,
    course_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    course = course_service.get_course(db, course_id)
    if course is None:
        raise NotFoundError("Course", course_id)

    # Resolve doc_ids: explicit list or all READY docs in the course
    if body.doc_ids:
        doc_ids = body.doc_ids
    else:
        from app.services.document_service import list_documents
        doc_ids = [
            d.id
            for d in list_documents(db, course_id)
            if d.status == DocumentStatus.READY
        ]

    if not doc_ids:
        raise ValidationError_(
            "No READY documents found. Upload and process at least one document first."
        )

    from app.services.outline_service import OUTLINE_PROMPT_VERSION

    run = GenerationRun(
        id=str(uuid.uuid4()),
        course_id=course_id,
        doc_ids_json=json.dumps(doc_ids),
        status=GenerationRunStatus.QUEUED,
        prompt_version=OUTLINE_PROMPT_VERSION,
        options_json=json.dumps(body.options) if body.options else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is not None:
        await arq_pool.enqueue_job(
            "generate_course_outline",
            course_id=course_id,
            doc_ids=doc_ids,
            run_id=run.id,
        )
    else:
        background_tasks.add_task(_run_outline_bg, course_id, doc_ids, run.id)

    return {"run_id": run.id, "status": run.status}


# ---------------------------------------------------------------------------
# GET /courses/{course_id}/outline
# ---------------------------------------------------------------------------

@router.get(
    "/courses/{course_id}/outline",
    response_model=OutlineResponse,
    summary="Get the draft course outline (chapters + lessons)",
)
def get_outline(
    course_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    course = course_service.get_course(db, course_id)
    if course is None:
        raise NotFoundError("Course", course_id)

    chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course_id, Chapter.status == "draft")
        .order_by(Chapter.order_index)
        .all()
    )

    return OutlineResponse(
        course_id=course_id,
        run_id=_latest_run_id(course_id, db),
        chapters=[_chapter_to_schema(ch) for ch in chapters],
    )


# ---------------------------------------------------------------------------
# PATCH /courses/{course_id}/outline
# ---------------------------------------------------------------------------

@router.patch(
    "/courses/{course_id}/outline",
    response_model=OutlineResponse,
    summary="Update draft outline: rename, reorder, or delete draft chapters/lessons",
)
def patch_outline(
    body: PatchOutlineBody,
    course_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    course = course_service.get_course(db, course_id)
    if course is None:
        raise NotFoundError("Course", course_id)

    for ch_patch in body.chapters:
        chapter = (
            db.query(Chapter)
            .filter(Chapter.id == ch_patch.id, Chapter.course_id == course_id)
            .first()
        )
        if chapter is None:
            continue

        if ch_patch.delete:
            for ls in db.query(Lesson).filter(Lesson.chapter_id == chapter.id).all():
                db.delete(ls)
            db.delete(chapter)
            db.flush()
            continue

        if ch_patch.title is not None:
            chapter.title = ch_patch.title
        if ch_patch.description is not None:
            chapter.description = ch_patch.description
        if ch_patch.order_index is not None:
            chapter.order_index = ch_patch.order_index

        for ls_patch in ch_patch.lessons:
            lesson = (
                db.query(Lesson)
                .filter(Lesson.id == ls_patch.id, Lesson.chapter_id == chapter.id)
                .first()
            )
            if lesson is None:
                continue
            if ls_patch.delete:
                db.delete(lesson)
                db.flush()
                continue
            if ls_patch.title is not None:
                lesson.title = ls_patch.title
            if ls_patch.description is not None:
                lesson.description = ls_patch.description
            if ls_patch.order_index is not None:
                lesson.order_index = ls_patch.order_index

    db.commit()

    # Return updated outline
    chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course_id, Chapter.status == "draft")
        .order_by(Chapter.order_index)
        .all()
    )
    return OutlineResponse(
        course_id=course_id,
        run_id=_latest_run_id(course_id, db),
        chapters=[_chapter_to_schema(ch) for ch in chapters],
    )


@router.post(
    "/courses/{course_id}/outline/actions",
    response_model=OutlineResponse,
    summary="Apply one manual outline editing operation",
)
def edit_outline(
    body: OutlineActionBody,
    course_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(_require_reviewer),
):
    if course_service.get_course(db, course_id) is None:
        raise NotFoundError("Course", course_id)

    from app.services.outline_edit_service import apply_action

    apply_action(db, course_id, body)
    chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course_id)
        .order_by(Chapter.order_index)
        .all()
    )
    return OutlineResponse(
        course_id=course_id,
        run_id=_latest_run_id(course_id, db),
        chapters=[_chapter_to_schema(ch) for ch in chapters],
    )


# ---------------------------------------------------------------------------
# GET /generation-runs/{run_id}
# ---------------------------------------------------------------------------

@router.get(
    "/generation-runs/{run_id}",
    response_model=GenerationRunSchema,
    summary="Poll a generation run for status and stage progress",
)
def get_generation_run(
    run_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
):
    run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
    if run is None:
        raise NotFoundError("GenerationRun", run_id)
    return GenerationRunSchema(
        id=run.id,
        course_id=run.course_id,
        status=run.status,
        stage=run.stage,
        error_message=run.error_message,
        prompt_version=run.prompt_version,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )
