"""Unit tests for quiz_generation.py — shared quiz generate/persist module."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Chapter,
    Course,
    OptionChoice,
    Question,
    Quiz,
    QuizAttempt,
    QuizScope,
    Section,
    User,
    UserRole,
)
from app.services.qvac_structured import StructuredGenerationError
from app.services.quiz_generation import generate_quiz_questions, persist_quiz


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    section = Section(id=str(uuid.uuid4()), title="Test")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), title="Test Course", section_id=section.id)
    db.add(course)
    chapter = Chapter(id=str(uuid.uuid4()), course_id=course.id, title="Ch", order_index=0)
    db.add(chapter)
    db.commit()
    return db, course, chapter


_QUESTIONS = [
    {
        "prompt": "What is a UTXO?",
        "options": [
            {"key": "A", "text": "An unspent transaction output"},
            {"key": "B", "text": "A mining reward"},
            {"key": "C", "text": "A block header"},
            {"key": "D", "text": "A wallet address"},
        ],
        "correct_key": "A",
        "concept_tag": "utxo-model",
        "difficulty": "beginner",
    }
]


# ---------------------------------------------------------------------------
# generate_quiz_questions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_quiz_questions_returns_schema_result():
    with patch(
        "app.services.quiz_generation.generate_json", new_callable=AsyncMock
    ) as mock_gj:
        mock_gj.return_value = {"questions": _QUESTIONS}
        result = await generate_quiz_questions("UTXO model", [{"label": "p1", "text": "..."}])

    assert result is not None
    assert result["questions"][0]["concept_tag"] == "utxo-model"


@pytest.mark.asyncio
async def test_generate_quiz_questions_returns_none_on_schema_failure():
    with patch(
        "app.services.quiz_generation.generate_json", new_callable=AsyncMock
    ) as mock_gj:
        mock_gj.side_effect = StructuredGenerationError("bad schema")
        result = await generate_quiz_questions("UTXO model", [{"label": "p1", "text": "..."}])

    assert result is None


# ---------------------------------------------------------------------------
# persist_quiz
# ---------------------------------------------------------------------------

def test_persist_quiz_creates_rows_with_concept_tags():
    db, course, chapter = _make_db()
    quiz = persist_quiz(
        db, _QUESTIONS, scope=QuizScope.COURSE, title="Quiz: UTXO", course_id=course.id,
    )

    assert quiz is not None
    assert quiz.course_id == course.id
    assert quiz.scope == QuizScope.COURSE

    questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()
    assert len(questions) == 1
    assert questions[0].concept_tag == "utxo-model"
    assert questions[0].difficulty == "beginner"

    opts = db.query(OptionChoice).filter(OptionChoice.question_id == questions[0].id).all()
    assert len(opts) == 4
    correct = [o for o in opts if o.is_correct]
    assert len(correct) == 1


def test_persist_quiz_returns_none_for_empty_questions():
    db, course, chapter = _make_db()
    quiz = persist_quiz(db, [], scope=QuizScope.COURSE, title="Empty", course_id=course.id)
    assert quiz is None


def test_persist_quiz_replaces_existing_for_same_course():
    db, course, chapter = _make_db()
    q1 = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="V1", course_id=course.id)
    q2 = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="V2", course_id=course.id)

    quizzes = db.query(Quiz).filter(Quiz.course_id == course.id).all()
    assert len(quizzes) == 1
    assert quizzes[0].id == q2.id
    assert quizzes[0].title == "V2"


def test_persist_quiz_replaces_existing_for_same_lesson():
    db, course, chapter = _make_db()
    from app.db.models import Lesson

    lesson = Lesson(id=str(uuid.uuid4()), chapter_id=chapter.id, title="L1", content="", order_index=0)
    db.add(lesson)
    db.commit()

    q1 = persist_quiz(db, _QUESTIONS, scope=QuizScope.LESSON, title="V1", lesson_id=lesson.id)
    q2 = persist_quiz(db, _QUESTIONS, scope=QuizScope.LESSON, title="V2", lesson_id=lesson.id)

    quizzes = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).all()
    assert len(quizzes) == 1
    assert quizzes[0].id == q2.id


def test_persist_quiz_uses_config_passing_score_by_default():
    from app.core.config import settings

    db, course, chapter = _make_db()
    quiz = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="Q", course_id=course.id)
    assert quiz.passing_score == settings.QUIZ_PASSING_SCORE


def test_persist_quiz_respects_explicit_passing_score():
    db, course, chapter = _make_db()
    quiz = persist_quiz(
        db, _QUESTIONS, scope=QuizScope.COURSE, title="Q", course_id=course.id, passing_score=85,
    )
    assert quiz.passing_score == 85


# ---------------------------------------------------------------------------
# persist_quiz — immutability once attempted (regression coverage for the
# FK-violation-on-replace bug found in code review: deleting a Question that
# an AttemptAnswer references would raise IntegrityError on a DB with FK
# enforcement, e.g. production PostgreSQL).
# ---------------------------------------------------------------------------

def test_persist_quiz_keeps_attempted_quiz_and_versions_alongside_it():
    db, course, chapter = _make_db()
    user = User(
        id=str(uuid.uuid4()), email=f"s-{uuid.uuid4()}@test.com", password_hash="x",
        display_name="S", role=UserRole.STUDENT,
    )
    db.add(user)
    db.commit()

    q1 = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="V1", course_id=course.id)
    q1_question = db.query(Question).filter(Question.quiz_id == q1.id).first()
    db.add(QuizAttempt(id=str(uuid.uuid4()), quiz_id=q1.id, user_id=user.id, score_pct=100, passed=True))
    db.commit()

    q2 = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="V2", course_id=course.id)

    # Old quiz and its attempted question survive — no FK violation, no lost history.
    assert db.query(Quiz).filter(Quiz.id == q1.id).first() is not None
    assert db.query(Question).filter(Question.id == q1_question.id).first() is not None
    assert db.query(QuizAttempt).filter(QuizAttempt.quiz_id == q1.id).count() == 1

    # New quiz was created alongside it, not in place of it.
    assert q2.id != q1.id
    quizzes = db.query(Quiz).filter(Quiz.course_id == course.id).all()
    assert len(quizzes) == 2
    assert {q.id for q in quizzes} == {q1.id, q2.id}


def test_persist_quiz_replaces_unattempted_quiz_even_if_an_older_one_was_attempted():
    """Only the quiz actually being replaced is checked for attempts — an
    older, already-superseded quiz's attempt history doesn't freeze the
    'current' slot forever."""
    db, course, chapter = _make_db()
    user = User(
        id=str(uuid.uuid4()), email=f"s-{uuid.uuid4()}@test.com", password_hash="x",
        display_name="S", role=UserRole.STUDENT,
    )
    db.add(user)
    db.commit()

    q1 = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="V1", course_id=course.id)
    db.add(QuizAttempt(id=str(uuid.uuid4()), quiz_id=q1.id, user_id=user.id, score_pct=100, passed=True))
    db.commit()

    q2 = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="V2", course_id=course.id)
    # q2 has no attempts yet — a third generation should replace q2 in place.
    q3 = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="V3", course_id=course.id)

    assert db.query(Quiz).filter(Quiz.id == q2.id).first() is None  # replaced
    assert db.query(Quiz).filter(Quiz.id == q1.id).first() is not None  # kept (attempted)
    assert db.query(Quiz).filter(Quiz.id == q3.id).first() is not None
    quizzes = db.query(Quiz).filter(Quiz.course_id == course.id).all()
    assert len(quizzes) == 2
