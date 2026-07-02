"""Content API — course builder phase 3, plus the phase-P2 review UI backend.

Endpoints:
  POST /courses/{id}/content/generate  → enqueue lesson content generation job
                                          (optionally scoped to lesson_ids —
                                          forces regeneration, bypasses cache)
  POST /courses/{id}/publish           → publish all ready chapters/lessons
  GET  /lessons/{id}/content           → lesson detail with content + quiz
  PATCH /lessons/{id}                  → instructor edit (title/description/content)
  POST /lessons/{id}/approve           → needs_review|draft → published
"""
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError_
from app.db.models import (
    Chapter,
    DocumentStatus,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
    Quiz,
    Question,
    OptionChoice,
    QuizScope,
    UserRole,
)
from app.db.session import get_db
from app.middleware.auth import CurrentUser
from app.services import course_service
from app.services import lesson_service

router = APIRouter(prefix="/api", tags=["Content"])

_require_reviewer = CurrentUser(roles=[UserRole.ADMIN, UserRole.INSTRUCTOR])


# ---------------------------------------------------------------------------
# Internal schemas (inline to avoid proliferating schema files)
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class OptionOut(BaseModel):
    """Options as seen by a student — never includes is_correct."""
    id: str
    label: str


class QuestionOut(BaseModel):
    id: str
    prompt: str
    order_index: int
    options: List[OptionOut]


class LessonQuizOut(BaseModel):
    id: str
    title: Optional[str]
    passing_score: int
    questions: List[QuestionOut]


class LessonContentOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    content: str
    status: Optional[str] = None
    order_index: int
    source_refs: List[str] = Field(default_factory=list)
    review_issues: List[str] = Field(default_factory=list)
    quiz: Optional[LessonQuizOut] = None


class PublishResult(BaseModel):
    published_chapters: int
    published_lessons: int
    skipped_chapters: int


class GenerateContentBody(BaseModel):
    lesson_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "Specific lesson IDs to (re)generate — forces regeneration by "
            "bypassing the content_hash cache. Defaults to all draft lessons."
        ),
    )


class LessonPatchBody(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    content: Optional[str] = Field(default=None, min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_content_bg(course_id: str, run_id: str, lesson_ids: Optional[List[str]] = None) -> None:
    """Async background task (fallback when ARQ is unavailable)."""
    from app.db.session import get_db_context

    with get_db_context() as db:
        await lesson_service.generate_course_content(
            course_id=course_id, db=db, run_id=run_id, lesson_ids=lesson_ids,
        )


def _quiz_for_lesson(lesson_id: str, db: Session) -> Optional[LessonQuizOut]:
    # quiz_generation.persist_quiz leaves an attempted quiz in place and
    # creates a new one alongside it (never deletes attempted history), so
    # more than one row can exist for this lesson — always take the newest.
    quiz = db.query(Quiz).filter(
        Quiz.lesson_id == lesson_id, Quiz.scope == QuizScope.LESSON
    ).order_by(Quiz.created_at.desc()).first()
    if quiz is None:
        return None

    questions = (
        db.query(Question)
        .filter(Question.quiz_id == quiz.id)
        .order_by(Question.order_index)
        .all()
    )
    q_out = []
    for q in questions:
        opts = (
            db.query(OptionChoice)
            .filter(OptionChoice.question_id == q.id)
            .all()
        )
        q_out.append(
            QuestionOut(
                id=q.id,
                prompt=q.prompt,
                order_index=q.order_index,
                options=[
                    OptionOut(id=o.id, label=o.label)
                    for o in opts
                ],
            )
        )
    return LessonQuizOut(
        id=quiz.id,
        title=quiz.title,
        passing_score=quiz.passing_score,
        questions=q_out,
    )


# ---------------------------------------------------------------------------
# POST /courses/{course_id}/content/generate
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/content/generate",
    status_code=202,
    summary="Start lesson content generation for all draft lessons in a course",
)
async def generate_content(
    request: Request,
    background_tasks: BackgroundTasks,
    body: GenerateContentBody,
    course_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
):
    course = course_service.get_course(db, course_id)
    if course is None:
        raise NotFoundError("Course", course_id)

    if body.lesson_ids:
        # Regeneration path: lessons may belong to already-published chapters
        # (e.g. re-running one lesson after an instructor edit upstream), so
        # don't require draft status — just that the lessons exist in this course.
        target_count = (
            db.query(Lesson)
            .join(Chapter, Lesson.chapter_id == Chapter.id)
            .filter(Chapter.course_id == course_id, Lesson.id.in_(body.lesson_ids))
            .count()
        )
        if target_count == 0:
            raise ValidationError_("None of the given lesson_ids belong to this course.")
        draft_count = target_count
    else:
        draft_count = (
            db.query(Lesson)
            .join(Chapter, Lesson.chapter_id == Chapter.id)
            .filter(Chapter.course_id == course_id, Chapter.status == "draft")
            .count()
        )
        if draft_count == 0:
            raise ValidationError_("No draft lessons found. Generate an outline first.")

    run = GenerationRun(
        id=str(uuid.uuid4()),
        course_id=course_id,
        doc_ids_json=json.dumps([]),
        status=GenerationRunStatus.QUEUED,
        prompt_version=lesson_service.CONTENT_PROMPT_VERSION,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is not None:
        await arq_pool.enqueue_job(
            "generate_course_content",
            course_id=course_id,
            run_id=run.id,
            lesson_ids=body.lesson_ids,
        )
    else:
        background_tasks.add_task(_run_content_bg, course_id, run.id, body.lesson_ids)

    return {"run_id": run.id, "status": run.status, "draft_lessons": draft_count}


# ---------------------------------------------------------------------------
# POST /courses/{course_id}/publish
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/publish",
    response_model=PublishResult,
    summary="Publish all chapters/lessons that passed groundedness check",
)
def publish_course(
    course_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
):
    course = course_service.get_course(db, course_id)
    if course is None:
        raise NotFoundError("Course", course_id)

    result = lesson_service.publish_course(course_id, db)
    return PublishResult(**result)


# ---------------------------------------------------------------------------
# GET /lessons/{lesson_id}/content
# ---------------------------------------------------------------------------

@router.get(
    "/lessons/{lesson_id}/content",
    response_model=LessonContentOut,
    summary="Get lesson content, metadata, and associated quiz",
)
def get_lesson_content(
    lesson_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if lesson is None:
        raise NotFoundError("Lesson", lesson_id)

    source_refs: List[str] = []
    if lesson.source_refs_json:
        try:
            source_refs = json.loads(lesson.source_refs_json)
        except json.JSONDecodeError:
            pass

    clean_content, issues = lesson_service.extract_issues(lesson.content or "")

    return LessonContentOut(
        id=lesson.id,
        title=lesson.title,
        description=lesson.description,
        content=clean_content,
        status=lesson.status,
        order_index=lesson.order_index,
        source_refs=source_refs,
        review_issues=issues,
        quiz=_quiz_for_lesson(lesson.id, db),
    )


# ---------------------------------------------------------------------------
# PATCH /lessons/{lesson_id} — instructor edit
# ---------------------------------------------------------------------------

@router.patch(
    "/lessons/{lesson_id}",
    response_model=LessonContentOut,
    summary="Edit a lesson's title, description, or content (instructor/admin only)",
)
def patch_lesson(
    body: LessonPatchBody,
    lesson_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(_require_reviewer),
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if lesson is None:
        raise NotFoundError("Lesson", lesson_id)

    if body.title is not None:
        lesson.title = body.title
    if body.description is not None:
        lesson.description = body.description
    if body.content is not None:
        # A manual edit is authoritative — it replaces the judge's issues
        # comment (there's nothing left to flag, the instructor already
        # reviewed it) and marks the content hash as up to date so a later
        # course-wide regeneration run doesn't silently overwrite the edit.
        lesson.content = body.content
        lesson.content_hash = lesson_service.compute_content_hash(lesson)

    db.commit()
    db.refresh(lesson)

    source_refs: List[str] = []
    if lesson.source_refs_json:
        try:
            source_refs = json.loads(lesson.source_refs_json)
        except json.JSONDecodeError:
            pass

    clean_content, issues = lesson_service.extract_issues(lesson.content or "")
    return LessonContentOut(
        id=lesson.id,
        title=lesson.title,
        description=lesson.description,
        content=clean_content,
        status=lesson.status,
        order_index=lesson.order_index,
        source_refs=source_refs,
        review_issues=issues,
        quiz=_quiz_for_lesson(lesson.id, db),
    )


# ---------------------------------------------------------------------------
# POST /lessons/{lesson_id}/approve
# ---------------------------------------------------------------------------

@router.post(
    "/lessons/{lesson_id}/approve",
    summary="Approve a lesson after manual review (instructor/admin only)",
)
def approve_lesson(
    lesson_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(_require_reviewer),
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if lesson is None:
        raise NotFoundError("Lesson", lesson_id)

    if not (lesson.content or "").strip():
        raise ValidationError_("Cannot approve a lesson with no content. Generate content first.")

    lesson.status = "published"
    db.commit()
    return {"id": lesson.id, "status": lesson.status}
