"""Quizzes API — generate, list, and evaluate quizzes.

Course-level quizzes (ad-hoc, generated from a free-text topic on the study
page) share the same DB-backed generation/persistence path as lesson quizzes
(course builder, see lesson_service.py) via quiz_generation.py. No quiz data
lives in memory; every attempt is persisted for analytics and for the
episodic-memory pipeline planned in docs/agent-memory-plan.md.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError_
from app.core.rate_limit import limiter
from app.db.models import (
    AttemptAnswer,
    OptionChoice,
    Question,
    Quiz,
    QuizAttempt,
    QuizScope,
)
from app.db.session import get_db
from app.core.config import TokenPayload
from app.middleware.auth import CurrentUser, get_current_user
from app.services import quiz_generation

router = APIRouter(prefix="/api", tags=["Quizzes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateQuizRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=500, description="Topic to quiz on")


class QuizSummary(BaseModel):
    id: str
    title: Optional[str]
    scope: str
    passing_score: int
    question_count: int


class StudentOptionOut(BaseModel):
    """Options as seen by a student before submitting an attempt — no is_correct."""
    id: str
    label: str


class StudentQuestionOut(BaseModel):
    id: str
    prompt: str
    qtype: str
    order_index: int
    options: List[StudentOptionOut]


class QuizDetail(BaseModel):
    id: str
    title: Optional[str]
    scope: str
    passing_score: int
    questions: List[StudentQuestionOut]


class SubmitAnswersRequest(BaseModel):
    answers: Dict[str, str] = Field(..., min_length=1)  # question_id → option_id


class AnswerCorrection(BaseModel):
    question_id: str
    correct_option_id: Optional[str]
    selected_option_id: Optional[str]
    is_correct: bool


class QuizAttemptResult(BaseModel):
    attempt_id: str
    score_pct: int
    passed: bool
    correct_count: int
    total_count: int
    corrections: List[AnswerCorrection]


class QuizAttemptSummary(BaseModel):
    attempt_id: str
    quiz_id: str
    quiz_title: Optional[str]
    score_pct: Optional[int]
    passed: Optional[bool]
    finished_at: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_student_detail(quiz: Quiz, questions: List[Question], db: Session) -> QuizDetail:
    out_questions = []
    for q in questions:
        opts = (
            db.query(OptionChoice)
            .filter(OptionChoice.question_id == q.id)
            .all()
        )
        out_questions.append(
            StudentQuestionOut(
                id=q.id,
                prompt=q.prompt,
                qtype=q.qtype,
                order_index=q.order_index,
                options=[StudentOptionOut(id=o.id, label=o.label) for o in opts],
            )
        )
    return QuizDetail(
        id=quiz.id,
        title=quiz.title,
        scope=quiz.scope,
        passing_score=quiz.passing_score,
        questions=out_questions,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/quizzes/generate",
    summary="Generate a quiz from course material",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def generate_quiz(
    request: Request,
    body: GenerateQuizRequest,
    course_id: str = Path(..., description="Course to generate quiz from"),
    _current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.schemas.study_schemas import StudyAction  # noqa: PLC0415
    from app.services import study_service  # noqa: PLC0415

    # Retrieval-only: no LLM call for the sources, so quiz generation costs
    # exactly one /generate_json call instead of a retrieval-answer + reparse.
    result = await study_service.dispatch(
        question=body.query,
        course_id=course_id,
        action=StudyAction.RETRIEVE,
    )

    context_items = [
        {"label": c.label or c.doc_id or f"ref_{i}", "text": c.snippet}
        for i, c in enumerate(result.citations)
    ]
    if not context_items:
        raise ValidationError_(
            "No source material found for this topic in the course. Try a broader query."
        )

    quiz_data = await quiz_generation.generate_quiz_questions(body.query, context_items)
    if not quiz_data or not quiz_data.get("questions"):
        raise ValidationError_(
            "Could not generate quiz questions from the course material. Try a more specific topic."
        )

    quiz = quiz_generation.persist_quiz(
        db,
        quiz_data["questions"],
        scope=QuizScope.COURSE,
        title=f"Quiz: {body.query[:60]}",
        course_id=course_id,
    )

    # persist_quiz returns None when handed an empty question list. That is
    # already ruled out above, but relying on it silently turns a future change
    # in quiz_generation into an AttributeError on quiz.id.
    if quiz is None:
        raise ValidationError_(
            "Could not persist the generated quiz. Try a more specific topic."
        )

    questions = (
        db.query(Question)
        .filter(Question.quiz_id == quiz.id)
        .order_by(Question.order_index)
        .all()
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_to_student_detail(quiz, questions, db).model_dump(),
    )


@router.get(
    "/courses/{course_id}/quizzes",
    summary="List generated quizzes for a course",
)
def list_quizzes(
    course_id: str = Path(..., description="Course ID"),
    _current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    quizzes = (
        db.query(Quiz)
        .filter(Quiz.scope == QuizScope.COURSE, Quiz.course_id == course_id)
        .order_by(Quiz.created_at.desc())
        .all()
    )
    summaries = [
        QuizSummary(
            id=q.id,
            title=q.title,
            scope=q.scope,
            passing_score=q.passing_score,
            question_count=db.query(Question).filter(Question.quiz_id == q.id).count(),
        ).model_dump()
        for q in quizzes
    ]
    return JSONResponse(status_code=status.HTTP_200_OK, content=summaries)


@router.get(
    "/quizzes/{quiz_id}",
    summary="Get quiz questions (without correct answers)",
)
def get_quiz(
    quiz_id: str = Path(..., description="Quiz ID"),
    _current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)

    questions = (
        db.query(Question)
        .filter(Question.quiz_id == quiz.id)
        .order_by(Question.order_index)
        .all()
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_to_student_detail(quiz, questions, db).model_dump(),
    )


@router.post(
    "/quizzes/{quiz_id}/attempts",
    summary="Submit quiz answers, persist the attempt, and receive score + corrections",
)
def submit_quiz(
    body: SubmitAnswersRequest,
    quiz_id: str = Path(..., description="Quiz ID"),
    current_user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)

    questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()
    total = len(questions)

    attempt = QuizAttempt(
        id=str(uuid.uuid4()),
        quiz_id=quiz.id,
        user_id=current_user.sub,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(attempt)
    db.flush()

    correct_count = 0
    corrections: List[AnswerCorrection] = []

    for question in questions:
        options = db.query(OptionChoice).filter(OptionChoice.question_id == question.id).all()
        correct_option = next((o for o in options if o.is_correct), None)
        selected_id = body.answers.get(question.id)
        selected_option = next((o for o in options if o.id == selected_id), None)

        is_correct = bool(
            selected_option is not None
            and correct_option is not None
            and selected_option.id == correct_option.id
        )
        if is_correct:
            correct_count += 1

        db.add(AttemptAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            selected_id=selected_option.id if selected_option else None,
            is_correct=is_correct,
        ))
        corrections.append(AnswerCorrection(
            question_id=question.id,
            correct_option_id=correct_option.id if correct_option else None,
            selected_option_id=selected_option.id if selected_option else None,
            is_correct=is_correct,
        ))

    score_pct = round(correct_count / total * 100) if total > 0 else 0
    passed = score_pct >= quiz.passing_score
    attempt.score_pct = score_pct
    attempt.passed = passed
    db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=QuizAttemptResult(
            attempt_id=attempt.id,
            score_pct=score_pct,
            passed=passed,
            correct_count=correct_count,
            total_count=total,
            corrections=corrections,
        ).model_dump(),
    )


@router.get(
    "/users/me/quiz-attempts",
    summary="List the current user's quiz attempts, optionally filtered by course",
)
def list_my_attempts(
    course_id: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    q = (
        db.query(QuizAttempt, Quiz)
        .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
        .filter(QuizAttempt.user_id == current_user.sub)
    )
    if course_id is not None:
        q = q.filter(Quiz.course_id == course_id)

    rows = q.order_by(QuizAttempt.finished_at.desc()).all()
    items = [
        QuizAttemptSummary(
            attempt_id=attempt.id,
            quiz_id=quiz.id,
            quiz_title=quiz.title,
            score_pct=attempt.score_pct,
            passed=attempt.passed,
            finished_at=attempt.finished_at,
        ).model_dump()
        for attempt, quiz in rows
    ]
    return JSONResponse(status_code=status.HTTP_200_OK, content=items)
