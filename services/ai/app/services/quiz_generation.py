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
from app.services.qvac_structured import StructuredGenerationError, generate_json

logger = logging.getLogger(__name__)

QUIZ_PROMPT_VERSION = "v2"  # v2 = adds concept_tag/difficulty to the schema

QUIZ_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 4,
            "items": {
                "type": "object",
                "required": [
                    "prompt", "options", "correct_key", "concept_tag", "difficulty",
                ],
                "properties": {
                    "prompt": {"type": "string"},
                    "options": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "required": ["key", "text"],
                            "properties": {
                                "key": {"type": "string", "enum": ["A", "B", "C", "D"]},
                                "text": {"type": "string"},
                            },
                        },
                    },
                    "correct_key": {"type": "string", "enum": ["A", "B", "C", "D"]},
                    "concept_tag": {
                        "type": "string",
                        "description": "short slug for the concept being tested, e.g. 'utxo-model'",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["beginner", "intermediate", "advanced"],
                    },
                },
            },
        }
    },
}

QUIZ_SYSTEM = (
    "You are an expert educator at BitPolito Academy creating assessment questions.\n"
    "RULES:\n"
    "1. Create 3-4 multiple-choice questions based ONLY on the provided source passages.\n"
    "2. Each question tests conceptual understanding, not trivial recall.\n"
    "3. All 4 options (A-D) must be plausible — wrong options should be conceptually close.\n"
    "4. The correct answer must be directly supported by the source text.\n"
    "5. Use exact technical terminology from the document.\n"
    "6. concept_tag: a short kebab-case slug identifying the single concept the question "
    "tests (e.g. 'utxo-model', 'proof-of-work', 'block-subsidy') — reuse the same tag "
    "across questions that test the same concept.\n"
    "7. difficulty: rate the question beginner / intermediate / advanced."
)


async def generate_quiz_questions(
    topic: str,
    context_items: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """Call /generate_json to produce MCQ quiz data with concept tags.

    Returns None (rather than raising) on schema-validation failure — quiz
    generation is treated as best-effort by all current callers.
    """
    prompt = (
        f'Generate a quiz on: "{topic}". '
        "Create 3-4 multiple-choice questions that test understanding of the key concepts "
        "in the provided source passages."
    )
    try:
        return await generate_json(
            prompt,
            QUIZ_SCHEMA,
            context=context_items,
            system_prompt=QUIZ_SYSTEM,
            generation_params={"temp": 0.3},
            task_type="content_gen",
        )
    except StructuredGenerationError as exc:
        logger.warning("Quiz generation failed for topic '%s': %s", topic, exc)
        return None


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
