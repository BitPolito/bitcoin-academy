"""Chapter test API — P5 of the course builder roadmap.

Endpoints:
  POST /chapters/{id}/test/generate  → build/version a test from lesson quizzes (instructor/admin)
  GET  /chapters/{id}/test           → current test, student-safe (no is_correct)

Submitting answers reuses POST /quizzes/{quiz_id}/attempts from quizzes_api.py —
a chapter test's synthesized quiz is a Quiz row like any other, so scoring,
persistence, and the corrections response all come for free.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError_
from app.db.models import Chapter, OptionChoice, Question, UserRole
from app.db.session import get_db
from app.middleware.auth import CurrentUser
from app.services import chapter_test_service

router = APIRouter(prefix="/api", tags=["Chapter Tests"])

_require_reviewer = CurrentUser(roles=[UserRole.ADMIN, UserRole.INSTRUCTOR])


class ChapterTestOptionOut(BaseModel):
    id: str
    label: str


class ChapterTestQuestionOut(BaseModel):
    id: str
    prompt: str
    order_index: int
    options: List[ChapterTestOptionOut]


class ChapterTestOut(BaseModel):
    id: str
    chapter_id: str
    title: str
    quiz_id: str
    passing_score: int
    questions: List[ChapterTestQuestionOut]


def _to_out(chapter_test, quiz, db: Session) -> ChapterTestOut:
    questions = (
        db.query(Question)
        .filter(Question.quiz_id == quiz.id)
        .order_by(Question.order_index)
        .all()
    )
    q_out = []
    for q in questions:
        opts = db.query(OptionChoice).filter(OptionChoice.question_id == q.id).all()
        q_out.append(ChapterTestQuestionOut(
            id=q.id,
            prompt=q.prompt,
            order_index=q.order_index,
            options=[ChapterTestOptionOut(id=o.id, label=o.label) for o in opts],
        ))
    return ChapterTestOut(
        id=chapter_test.id,
        chapter_id=chapter_test.chapter_id,
        title=chapter_test.title,
        quiz_id=quiz.id,
        passing_score=quiz.passing_score,
        questions=q_out,
    )


@router.post(
    "/chapters/{chapter_id}/test/generate",
    response_model=ChapterTestOut,
    summary="Build (or version) a chapter test from its lessons' quizzes (instructor/admin only)",
)
def generate_chapter_test(
    chapter_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(_require_reviewer),
):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if chapter is None:
        raise NotFoundError("Chapter", chapter_id)

    chapter_test = chapter_test_service.build_chapter_test(db, chapter_id)
    if chapter_test is None:
        raise ValidationError_(
            "No published lessons with a generated quiz in this chapter yet."
        )

    quiz = chapter_test_service.get_chapter_test_quiz(db, chapter_test)
    return _to_out(chapter_test, quiz, db)


@router.get(
    "/chapters/{chapter_id}/test",
    response_model=ChapterTestOut,
    summary="Get the current chapter test (student-safe, no correct answers)",
)
def get_chapter_test(
    chapter_id: str = Path(..., min_length=1, max_length=36),
    db: Session = Depends(get_db),
):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if chapter is None:
        raise NotFoundError("Chapter", chapter_id)

    chapter_test = chapter_test_service.get_current_chapter_test(db, chapter_id)
    if chapter_test is None:
        raise NotFoundError("ChapterTest", chapter_id)

    quiz = chapter_test_service.get_chapter_test_quiz(db, chapter_test)
    if quiz is None:
        raise NotFoundError("ChapterTest", chapter_id)
    return _to_out(chapter_test, quiz, db)
