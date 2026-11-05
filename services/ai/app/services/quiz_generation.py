"""Shared quiz generation + persistence — used by the course builder (per-lesson
quizzes) and by the study page (ad-hoc quizzes on a free-text topic).

Replaces two previously-diverging implementations:
  - lesson_service._generate_quiz_data / _persist_quiz (course builder, DB-backed)
  - quizzes_api._parse_quiz_text (study page, regex over free text, in-memory)

All generation goes through /generate_json — no free-text parsing anywhere.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import OptionChoice, Question, QuestionType, Quiz, QuizAttempt, QuizScope
from app.services import quiz_harness

logger = logging.getLogger(__name__)

_DEFAULT_TARGET_COUNT = quiz_harness.DEFAULT_TARGET_COUNT


async def generate_quiz_questions(
    topic: str,
    context_items: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Run the plan/generate/critique/repair harness to produce MCQ quiz data.

    Always returns the full `{"questions": [...], "trace": {...}}` dict from
    the harness, even when `questions` is empty — the trace is most valuable
    exactly in that case (issue #134's "surface rejected questions"
    acceptance criterion), and callers that check `.get("questions")` or do
    `if quiz_data:` already treat an empty-questions dict as "no quiz" since
    it is still truthy, so this never changes caller behaviour.
    """
    result = await quiz_harness.run(topic, context_items, target_count=_DEFAULT_TARGET_COUNT)
    if not result["questions"]:
        logger.warning(
            "Quiz generation for '%s' produced no questions: %s", topic, result["trace"]
        )
    return result


def persist_quiz(
    db: Session,
    questions: List[Dict[str, Any]],
    scope: QuizScope,
    title: str,
    *,
    lesson_id: Optional[str] = None,
    course_id: Optional[str] = None,
    passing_score: Optional[int] = None,
) -> Optional[Quiz]:
    """Write Quiz / Question / OptionChoice rows.

    Replaces any existing quiz with the same scope + target (lesson_id or
    course_id) — a course/lesson has at most one "live" generated quiz at a
    time — UNLESS that quiz already has recorded QuizAttempt rows. Deleting
    an attempted quiz's Questions would either violate the (unenforced-in-
    SQLite-but-real-on-Postgres) FK from AttemptAnswer.question_id, or
    silently destroy a student's attempt history. When attempts exist, the
    old quiz is left in place and the new one is created alongside it,
    mirroring the immutability-once-attempted rule already used for chapter
    tests (see chapter_test_service.build_chapter_test). Callers that need
    "the current quiz" order by created_at desc (see content_api._quiz_for_lesson).

    Returns None if *questions* is empty.
    """
    if not questions:
        return None

    # COURSE-scoped quizzes are ad-hoc, per-request study quizzes with no
    # single owner: replacing "the newest unattempted one" would let one user's
    # generate call delete another user's in-progress quiz (their later submit
    # then 404s). Only the single-writer instructor flows (LESSON / CHAPTER_TEST)
    # get the replace-in-place behaviour; COURSE always appends.
    existing = None
    if scope != QuizScope.COURSE:
        existing_q = db.query(Quiz).filter(Quiz.scope == scope)
        if lesson_id is not None:
            existing_q = existing_q.filter(Quiz.lesson_id == lesson_id)
        if course_id is not None:
            existing_q = existing_q.filter(Quiz.course_id == course_id)
        existing = existing_q.order_by(Quiz.created_at.desc()).first()
    if existing:
        has_attempts = (
            db.query(QuizAttempt).filter(QuizAttempt.quiz_id == existing.id).first()
            is not None
        )
        if not has_attempts:
            for q in db.query(Question).filter(Question.quiz_id == existing.id).all():
                db.query(OptionChoice).filter(OptionChoice.question_id == q.id).delete()
                db.delete(q)
            db.delete(existing)
            db.flush()

    quiz = Quiz(
        id=str(uuid.uuid4()),
        scope=scope,
        title=title[:120],
        passing_score=passing_score if passing_score is not None else settings.QUIZ_PASSING_SCORE,
        lesson_id=lesson_id,
        course_id=course_id,
        # Explicit microsecond-precision timestamp — SQLite's func.now()
        # default has 1-second resolution, ambiguous for list_quizzes'
        # created_at ordering when quizzes are generated back to back.
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(quiz)
    db.flush()

    for order_idx, q_data in enumerate(questions):
        question = Question(
            id=str(uuid.uuid4()),
            quiz_id=quiz.id,
            qtype=QuestionType.MCQ,
            prompt=q_data["prompt"],
            order_index=order_idx,
            concept_tag=q_data.get("concept_tag"),
            difficulty=q_data.get("difficulty"),
            source_ref=q_data.get("chunk_id"),
        )
        db.add(question)
        db.flush()

        correct_key = q_data.get("correct_key", "A")
        for opt in q_data.get("options", []):
            choice = OptionChoice(
                id=str(uuid.uuid4()),
                question_id=question.id,
                label=f"{opt['key']}) {opt['text']}",
                is_correct=(opt["key"] == correct_key),
            )
            db.add(choice)

    db.commit()
    db.refresh(quiz)
    return quiz
