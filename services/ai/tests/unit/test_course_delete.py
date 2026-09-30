"""Unit tests for the full course deletion cascade — P4.

Covers: quizzes (lesson/course/chapter-test scoped), attempts, chapters,
lessons, generation runs, progress, certificate revocation (not deletion),
and document cleanup (chunk_parent + file removal).
"""
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AttemptAnswer,
    Base,
    Certificate,
    Chapter,
    ChapterTest,
    ChapterTestQuiz,
    ChunkParent,
    Course,
    CourseDocument,
    DocumentStatus,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
    OptionChoice,
    Question,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizScope,
    Section,
    User,
    UserCourseProgress,
    UserLessonProgress,
    UserRole,
)
from app.services import course_service


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _full_course(db):
    """Build a course with one of everything: document, chunk, chapter,
    lesson, lesson quiz + attempt, course-scoped quiz, chapter test,
    generation run, progress, certificate."""
    section = Section(id=str(uuid.uuid4()), title="Sec")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), title="Full Course", section_id=section.id)
    db.add(course)
    user = User(
        id=str(uuid.uuid4()), email=f"s-{uuid.uuid4()}@test.com", password_hash="x",
        display_name="S", role=UserRole.STUDENT,
    )
    db.add(user)
    db.commit()

    doc = CourseDocument(
        id=str(uuid.uuid4()), course_id=course.id, filename="doc.pdf",
        size=100, status=DocumentStatus.READY,
    )
    db.add(doc)
    chunk = ChunkParent(id=str(uuid.uuid4()), doc_id=doc.id, course_id=course.id, text="Bitcoin.")
    db.add(chunk)

    chapter = Chapter(id=str(uuid.uuid4()), course_id=course.id, title="Ch1", order_index=0)
    db.add(chapter)
    db.flush()
    lesson = Lesson(id=str(uuid.uuid4()), chapter_id=chapter.id, title="L1", content="c", order_index=0)
    db.add(lesson)
    db.flush()

    # Lesson-scoped quiz + attempt
    lesson_quiz = Quiz(id=str(uuid.uuid4()), scope=QuizScope.LESSON, title="LQ", lesson_id=lesson.id)
    db.add(lesson_quiz)
    db.flush()
    lq_question = Question(id=str(uuid.uuid4()), quiz_id=lesson_quiz.id, qtype=QuestionType.MCQ, prompt="Q?", order_index=0)
    db.add(lq_question)
    db.flush()
    lq_opt = OptionChoice(id=str(uuid.uuid4()), question_id=lq_question.id, label="A", is_correct=True)
    db.add(lq_opt)
    db.flush()
    attempt = QuizAttempt(id=str(uuid.uuid4()), quiz_id=lesson_quiz.id, user_id=user.id, score_pct=100, passed=True)
    db.add(attempt)
    db.flush()
    db.add(AttemptAnswer(attempt_id=attempt.id, question_id=lq_question.id, selected_id=lq_opt.id, is_correct=True))

    # Course-scoped ad-hoc quiz
    course_quiz = Quiz(id=str(uuid.uuid4()), scope=QuizScope.COURSE, title="CQ", course_id=course.id)
    db.add(course_quiz)
    db.flush()
    cq_question = Question(id=str(uuid.uuid4()), quiz_id=course_quiz.id, qtype=QuestionType.MCQ, prompt="Q2?", order_index=0)
    db.add(cq_question)

    # Chapter test wrapping the lesson quiz
    ch_test = ChapterTest(id=str(uuid.uuid4()), chapter_id=chapter.id, title="Test1")
    db.add(ch_test)
    db.flush()
    db.add(ChapterTestQuiz(chapter_test_id=ch_test.id, quiz_id=lesson_quiz.id, order_index=0))

    run = GenerationRun(
        id=str(uuid.uuid4()), course_id=course.id, doc_ids_json="[]",
        status=GenerationRunStatus.DONE, created_at="2026-01-01T00:00:00Z",
    )
    db.add(run)

    db.add(UserCourseProgress(user_id=user.id, course_id=course.id, percent=100))
    db.add(UserLessonProgress(user_id=user.id, lesson_id=lesson.id, status="completed"))

    unique = uuid.uuid4().hex[:8]
    cert = Certificate(
        id=str(uuid.uuid4()), user_id=user.id, course_id=course.id, code=f"ABC{unique}",
        verification_hash=f"h-{unique}", revoked=False,
    )
    db.add(cert)
    db.commit()

    return {
        "course": course, "doc": doc, "chunk": chunk, "chapter": chapter,
        "lesson": lesson, "lesson_quiz": lesson_quiz, "course_quiz": course_quiz,
        "chapter_test": ch_test, "run": run, "cert": cert, "user": user,
        "attempt": attempt,
    }


@patch("app.services.document_service._qvac_delete_workspace_chunks")
def test_delete_course_removes_all_child_rows(mock_qvac, tmp_path):
    db = _make_db()
    entities = _full_course(db)
    # Snapshot ids as plain strings before deleting — the ORM objects
    # themselves get expired by the bulk deletes and would raise
    # ObjectDeletedError if their attributes were accessed afterwards.
    ids = {k: v.id for k, v in entities.items()}
    course_id = ids["course"]

    with patch("app.workers.pipeline.UPLOADS_DIR", tmp_path):
        counts = course_service.delete_course(db, course_id)

    assert counts is not None
    assert counts["documents"] == 1
    assert counts["certificates_revoked"] == 1

    assert db.query(CourseDocument).filter(CourseDocument.id == ids["doc"]).first() is None
    assert db.query(ChunkParent).filter(ChunkParent.id == ids["chunk"]).first() is None
    assert db.query(Chapter).filter(Chapter.id == ids["chapter"]).first() is None
    assert db.query(Lesson).filter(Lesson.id == ids["lesson"]).first() is None
    assert db.query(Quiz).filter(Quiz.id == ids["lesson_quiz"]).first() is None
    assert db.query(Quiz).filter(Quiz.id == ids["course_quiz"]).first() is None
    assert db.query(ChapterTest).filter(ChapterTest.id == ids["chapter_test"]).first() is None
    assert db.query(ChapterTestQuiz).filter(
        ChapterTestQuiz.chapter_test_id == ids["chapter_test"]
    ).first() is None
    assert db.query(GenerationRun).filter(GenerationRun.id == ids["run"]).first() is None
    assert db.query(QuizAttempt).filter(QuizAttempt.id == ids["attempt"]).first() is None
    assert db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == ids["attempt"]).first() is None
    assert db.query(UserCourseProgress).filter(UserCourseProgress.course_id == course_id).first() is None
    assert db.query(UserLessonProgress).filter(
        UserLessonProgress.lesson_id == ids["lesson"]
    ).first() is None


@patch("app.services.document_service._qvac_delete_workspace_chunks")
def test_delete_course_revokes_not_deletes_certificates(mock_qvac, tmp_path):
    db = _make_db()
    entities = _full_course(db)
    course_id = entities["course"].id

    with patch("app.workers.pipeline.UPLOADS_DIR", tmp_path):
        course_service.delete_course(db, course_id)

    cert = db.query(Certificate).filter(Certificate.id == entities["cert"].id).first()
    assert cert is not None  # still exists — not deleted
    assert cert.revoked is True


@patch("app.services.document_service._qvac_delete_workspace_chunks")
def test_delete_course_soft_deletes_course_row(mock_qvac, tmp_path):
    db = _make_db()
    entities = _full_course(db)
    course_id = entities["course"].id

    with patch("app.workers.pipeline.UPLOADS_DIR", tmp_path):
        course_service.delete_course(db, course_id)

    course = db.query(Course).filter(Course.id == course_id).first()
    assert course is not None
    assert course.is_active is False


@patch("app.services.document_service._qvac_delete_workspace_chunks")
def test_delete_course_removes_uploaded_file(mock_qvac, tmp_path):
    db = _make_db()
    entities = _full_course(db)
    course_id = entities["course"].id
    doc_id = entities["doc"].id

    course_dir = tmp_path / course_id
    course_dir.mkdir(parents=True)
    uploaded_file = course_dir / f"{doc_id}_doc.pdf"
    uploaded_file.write_bytes(b"%PDF-1.4 fake")
    assert uploaded_file.exists()

    with patch("app.workers.pipeline.UPLOADS_DIR", tmp_path):
        course_service.delete_course(db, course_id)

    assert not uploaded_file.exists()


def test_delete_course_returns_none_for_unknown_course():
    db = _make_db()
    result = course_service.delete_course(db, "nonexistent-course-id")
    assert result is None


@patch("app.services.document_service._qvac_delete_workspace_chunks")
def test_delete_course_does_not_touch_other_courses(mock_qvac, tmp_path):
    db = _make_db()
    entities_a = _full_course(db)
    entities_b = _full_course(db)

    with patch("app.workers.pipeline.UPLOADS_DIR", tmp_path):
        course_service.delete_course(db, entities_a["course"].id)

    # Course B's data must be untouched
    assert db.query(Chapter).filter(Chapter.id == entities_b["chapter"].id).first() is not None
    assert db.query(Lesson).filter(Lesson.id == entities_b["lesson"].id).first() is not None
    assert db.query(Quiz).filter(Quiz.id == entities_b["lesson_quiz"].id).first() is not None
    cert_b = db.query(Certificate).filter(Certificate.id == entities_b["cert"].id).first()
    assert cert_b.revoked is False


# ---------------------------------------------------------------------------
# Atomicity — regression coverage for a code-review-found bug: document
# deletions used to commit individually inside the loop, so a later failure
# in the DB cascade left some documents permanently gone while the course
# and its chapters/lessons/quizzes survived. Everything must now be part of
# one transaction, committed once at the end.
# ---------------------------------------------------------------------------

@patch("app.services.document_service._qvac_delete_workspace_chunks")
def test_delete_course_is_atomic_on_mid_cascade_failure(mock_qvac, tmp_path):
    db = _make_db()
    entities = _full_course(db)
    course_id = entities["course"].id
    doc_id = entities["doc"].id
    chapter_id = entities["chapter"].id

    with patch("app.workers.pipeline.UPLOADS_DIR", tmp_path), patch(
        "app.services.course_service.course_repo.delete_course_cascade",
        side_effect=RuntimeError("simulated mid-cascade failure"),
    ):
        with pytest.raises(RuntimeError):
            course_service.delete_course(db, course_id)

    # Nothing was committed — roll back whatever the session accumulated,
    # exactly as a FastAPI request teardown would on an unhandled exception,
    # then verify the document (deleted earlier in the same call, before the
    # cascade raised) is still there.
    db.rollback()

    assert db.query(CourseDocument).filter(CourseDocument.id == doc_id).first() is not None
    assert db.query(Chapter).filter(Chapter.id == chapter_id).first() is not None
    course = db.query(Course).filter(Course.id == course_id).first()
    assert course.is_active is True
