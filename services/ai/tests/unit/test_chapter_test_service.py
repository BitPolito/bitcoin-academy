"""Unit tests for chapter_test_service.py — P5, zero-LLM chapter tests
built by selecting from already-generated lesson quizzes."""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Chapter,
    ChapterTest,
    ChapterTestQuiz,
    Course,
    Lesson,
    OptionChoice,
    Question,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizScope,
    Section,
    User,
    UserRole,
)
from app.services import chapter_test_service


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _seed_chapter(db, n_lessons=2, questions_per_lesson=3, published=True):
    section = Section(id=str(uuid.uuid4()), title="Sec")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), title="Course", section_id=section.id)
    db.add(course)
    chapter = Chapter(id=str(uuid.uuid4()), course_id=course.id, title="Chapter 1", order_index=0)
    db.add(chapter)
    db.commit()

    lessons = []
    for i in range(n_lessons):
        lesson = Lesson(
            id=str(uuid.uuid4()), chapter_id=chapter.id, title=f"Lesson {i}",
            content="content", order_index=i,
            status="published" if published else "draft",
        )
        db.add(lesson)
        db.flush()
        lessons.append(lesson)

        quiz = Quiz(id=str(uuid.uuid4()), scope=QuizScope.LESSON, title=f"Q{i}", lesson_id=lesson.id)
        db.add(quiz)
        db.flush()
        for j in range(questions_per_lesson):
            q = Question(
                id=str(uuid.uuid4()), quiz_id=quiz.id, qtype=QuestionType.MCQ,
                prompt=f"L{i}Q{j}?", order_index=j,
                concept_tag=f"concept-{i}-{j}", difficulty="beginner",
            )
            db.add(q)
            db.flush()
            for k, key in enumerate(["A", "B", "C", "D"]):
                db.add(OptionChoice(
                    id=str(uuid.uuid4()), question_id=q.id, label=f"{key}) opt",
                    is_correct=(k == 0),
                ))
    db.commit()
    return chapter, lessons


# ---------------------------------------------------------------------------
# build_chapter_test
# ---------------------------------------------------------------------------

def test_build_chapter_test_creates_test_and_quiz():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=2, questions_per_lesson=3)

    ct = chapter_test_service.build_chapter_test(db, chapter.id)

    assert ct is not None
    assert ct.chapter_id == chapter.id

    quiz = chapter_test_service.get_chapter_test_quiz(db, ct)
    assert quiz is not None
    assert quiz.scope == QuizScope.CHAPTER_TEST


def test_build_chapter_test_caps_per_lesson_and_total():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=2, questions_per_lesson=5)

    ct = chapter_test_service.build_chapter_test(db, chapter.id)
    quiz = chapter_test_service.get_chapter_test_quiz(db, ct)
    questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()

    assert len(questions) <= chapter_test_service.MAX_QUESTIONS_PER_TEST
    # Max 2 per lesson: with 2 lessons x 5 questions each, expect exactly 4
    assert len(questions) == 4


def test_build_chapter_test_copies_are_independent_rows():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=1, questions_per_lesson=2)

    original_quiz = db.query(Quiz).filter(Quiz.lesson_id == lessons[0].id).first()
    original_question_ids = {
        q.id for q in db.query(Question).filter(Question.quiz_id == original_quiz.id).all()
    }

    ct = chapter_test_service.build_chapter_test(db, chapter.id)
    test_quiz = chapter_test_service.get_chapter_test_quiz(db, ct)
    copied_ids = {q.id for q in db.query(Question).filter(Question.quiz_id == test_quiz.id).all()}

    assert copied_ids.isdisjoint(original_question_ids)
    # Original quiz questions still exist, untouched
    assert db.query(Question).filter(Question.quiz_id == original_quiz.id).count() == 2


def test_build_chapter_test_does_not_skip_reachable_questions_across_lessons():
    """Regression test for a code-review-found bug: the round-robin used to
    advance a single shared position pointer across all lessons, so picking
    a later-positioned question in one lesson (via the concept_tag
    preference) could push that lesson's pointer past an earlier, still
    unselected, still-under-cap question in a DIFFERENT lesson — silently
    under-filling the test even though both lessons had enough headroom."""
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=2, questions_per_lesson=2)
    lesson_a, lesson_b = lessons

    qs_a = db.query(Question).filter(
        Question.quiz_id == db.query(Quiz).filter(Quiz.lesson_id == lesson_a.id).first().id
    ).order_by(Question.order_index).all()
    qs_b = db.query(Question).filter(
        Question.quiz_id == db.query(Quiz).filter(Quiz.lesson_id == lesson_b.id).first().id
    ).order_by(Question.order_index).all()

    # Lesson A: both questions share a tag (no diversity choice possible).
    qs_a[0].concept_tag = "consensus"
    qs_a[1].concept_tag = "consensus"
    # Lesson B: first question duplicates lesson A's tag, second is unique —
    # this is exactly what makes the preference logic pick position 1
    # before position 0, which is what triggered the old bug.
    qs_b[0].concept_tag = "consensus"
    qs_b[1].concept_tag = "mining"
    db.commit()

    ct = chapter_test_service.build_chapter_test(db, chapter.id)
    quiz = chapter_test_service.get_chapter_test_quiz(db, ct)
    selected = db.query(Question).filter(Question.quiz_id == quiz.id).all()

    # Both lessons have 2 questions and the cap is 2/lesson — every question
    # should be selected (4 total), none silently dropped. build_chapter_test
    # copies questions into new rows (new ids), so compare by prompt text —
    # the identifying content of the original questions.
    assert len(selected) == 4
    selected_prompts = {q.prompt for q in selected}
    assert selected_prompts == {qs_a[0].prompt, qs_a[1].prompt, qs_b[0].prompt, qs_b[1].prompt}


def test_build_chapter_test_returns_none_for_unknown_chapter():
    db = _make_db()
    assert chapter_test_service.build_chapter_test(db, "nonexistent") is None


def test_build_chapter_test_returns_none_without_published_lessons():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=2, questions_per_lesson=2, published=False)
    assert chapter_test_service.build_chapter_test(db, chapter.id) is None


def test_build_chapter_test_diversifies_concept_tags_when_possible():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=1, questions_per_lesson=4)
    # Make first two questions share a concept_tag, rest distinct
    qs = db.query(Question).filter(Question.quiz_id == db.query(Quiz).filter(
        Quiz.lesson_id == lessons[0].id).first().id).order_by(Question.order_index).all()
    qs[0].concept_tag = "dup"
    qs[1].concept_tag = "dup"
    qs[2].concept_tag = "unique-1"
    qs[3].concept_tag = "unique-2"
    db.commit()

    ct = chapter_test_service.build_chapter_test(db, chapter.id)
    quiz = chapter_test_service.get_chapter_test_quiz(db, ct)
    selected = db.query(Question).filter(Question.quiz_id == quiz.id).all()

    # Max 2 per lesson cap still applies — only 2 selected total
    assert len(selected) == 2
    tags = {q.concept_tag for q in selected}
    # Prefers diverse tags: should not both be "dup" when unique alternatives exist
    assert tags != {"dup"}


# ---------------------------------------------------------------------------
# Versioning: replace vs new version
# ---------------------------------------------------------------------------

def test_rebuild_without_attempts_replaces_previous_test():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=1, questions_per_lesson=2)

    ct1 = chapter_test_service.build_chapter_test(db, chapter.id)
    ct1_id = ct1.id
    quiz1 = chapter_test_service.get_chapter_test_quiz(db, ct1)
    quiz1_id = quiz1.id

    ct2 = chapter_test_service.build_chapter_test(db, chapter.id)

    assert db.query(ChapterTest).filter(ChapterTest.id == ct1_id).first() is None
    assert db.query(Quiz).filter(Quiz.id == quiz1_id).first() is None
    assert db.query(ChapterTest).filter(ChapterTest.chapter_id == chapter.id).count() == 1
    assert ct2.id != ct1_id


def test_rebuild_with_attempts_keeps_previous_test_as_history():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=1, questions_per_lesson=2)
    user = User(
        id=str(uuid.uuid4()), email="s@test.com", password_hash="x",
        display_name="S", role=UserRole.STUDENT,
    )
    db.add(user)
    db.commit()

    ct1 = chapter_test_service.build_chapter_test(db, chapter.id)
    quiz1 = chapter_test_service.get_chapter_test_quiz(db, ct1)
    db.add(QuizAttempt(id=str(uuid.uuid4()), quiz_id=quiz1.id, user_id=user.id, score_pct=100, passed=True))
    db.commit()
    ct1_id = ct1.id
    quiz1_id = quiz1.id

    ct2 = chapter_test_service.build_chapter_test(db, chapter.id)

    # Old test + quiz still exist (attempt history preserved)
    assert db.query(ChapterTest).filter(ChapterTest.id == ct1_id).first() is not None
    assert db.query(Quiz).filter(Quiz.id == quiz1_id).first() is not None
    assert db.query(ChapterTest).filter(ChapterTest.chapter_id == chapter.id).count() == 2
    assert ct2.id != ct1_id


def test_get_current_chapter_test_returns_newest():
    db = _make_db()
    chapter, lessons = _seed_chapter(db, n_lessons=1, questions_per_lesson=2)
    user = User(
        id=str(uuid.uuid4()), email="s2@test.com", password_hash="x",
        display_name="S", role=UserRole.STUDENT,
    )
    db.add(user)
    db.commit()

    ct1 = chapter_test_service.build_chapter_test(db, chapter.id)
    quiz1 = chapter_test_service.get_chapter_test_quiz(db, ct1)
    db.add(QuizAttempt(id=str(uuid.uuid4()), quiz_id=quiz1.id, user_id=user.id, score_pct=50, passed=False))
    db.commit()

    ct2 = chapter_test_service.build_chapter_test(db, chapter.id)

    current = chapter_test_service.get_current_chapter_test(db, chapter.id)
    assert current.id == ct2.id


def test_get_current_chapter_test_none_when_never_built():
    db = _make_db()
    chapter, _ = _seed_chapter(db, n_lessons=1, questions_per_lesson=2)
    assert chapter_test_service.get_current_chapter_test(db, chapter.id) is None
