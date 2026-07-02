"""Integration tests for content_api — Phase 3 course builder.

Uses TestClient (ASGI) with an in-memory SQLite DB injected via dependency_overrides.
All LLM calls are mocked via patch so tests are fully deterministic.
"""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Chapter,
    ChunkParent,
    Course,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
    OptionChoice,
    Question,
    QuestionType,
    Quiz,
    QuizScope,
    Section,
)
from app.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture()
def client(db_session):
    """TestClient with DB override and ARQ pool set to None.

    Intentionally avoids `with TestClient(app) as c` so that the ASGI lifespan
    is NOT triggered — lifespan calls init_db() against the real on-disk DB,
    which is irrelevant (and fragile) during unit/integration tests.
    """
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    app.state.arq_pool = None  # force BackgroundTasks path
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _seed_course(db):
    section = Section(id=str(uuid.uuid4()), title="Test")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), title="Test Course", section_id=section.id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _seed_draft_chapter(db, course_id):
    ch = Chapter(
        id=str(uuid.uuid4()),
        course_id=course_id,
        title="Chapter 1",
        order_index=0,
        status="draft",
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _seed_lesson(db, chapter_id, source_refs=None, status="draft", content=""):
    ls = Lesson(
        id=str(uuid.uuid4()),
        chapter_id=chapter_id,
        title="Lesson 1",
        content=content,
        order_index=0,
        status=status,
        source_refs_json=json.dumps(source_refs) if source_refs else None,
    )
    db.add(ls)
    db.commit()
    db.refresh(ls)
    return ls


def _seed_parent(db, cid, course_id, text="Bitcoin is a peer-to-peer cash system."):
    p = ChunkParent(
        id=cid,
        doc_id="doc1",
        course_id=course_id,
        text=text,
    )
    db.add(p)
    db.commit()
    return p


# ---------------------------------------------------------------------------
# POST /courses/{id}/content/generate
# ---------------------------------------------------------------------------

class TestGenerateContent:
    def test_returns_202_with_run_id(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_draft_chapter(db_session, course.id)
        _seed_lesson(db_session, ch.id, source_refs=["p1"])

        # Prevent the background task from running in a separate DB context
        with patch("app.api.content_api._run_content_bg", new_callable=AsyncMock):
            resp = client.post(
                f"/api/courses/{course.id}/content/generate", json={}
            )
        assert resp.status_code == 202
        body = resp.json()
        assert "run_id" in body
        assert body["status"] == GenerationRunStatus.QUEUED
        assert body["draft_lessons"] == 1

        run = db_session.query(GenerationRun).filter(
            GenerationRun.id == body["run_id"]
        ).first()
        assert run is not None
        assert run.course_id == course.id

    def test_422_when_no_draft_lessons(self, client, db_session):
        course = _seed_course(db_session)
        # Chapter is published — lessons won't appear in draft count
        ch = Chapter(
            id=str(uuid.uuid4()),
            course_id=course.id,
            title="Ch",
            order_index=0,
            status="published",
        )
        db_session.add(ch)
        db_session.commit()
        _seed_lesson(db_session, ch.id)

        resp = client.post(
            f"/api/courses/{course.id}/content/generate", json={}
        )
        assert resp.status_code == 422

    def test_404_when_course_not_found(self, client, db_session):
        resp = client.post(
            "/api/courses/nonexistent-course/content/generate", json={}
        )
        assert resp.status_code == 404

    def test_422_when_course_has_no_chapters(self, client, db_session):
        course = _seed_course(db_session)
        resp = client.post(
            f"/api/courses/{course.id}/content/generate", json={}
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /courses/{id}/publish
# ---------------------------------------------------------------------------

class TestPublishCourse:
    def test_publishes_chapters_with_all_published_lessons(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_draft_chapter(db_session, course.id)
        _seed_lesson(db_session, ch.id, status="published", content="good")
        _seed_lesson(db_session, ch.id, status="published", content="good")

        resp = client.post(f"/api/courses/{course.id}/publish")
        assert resp.status_code == 200
        body = resp.json()
        assert body["published_chapters"] == 1
        assert body["published_lessons"] == 2
        assert body["skipped_chapters"] == 0

        db_session.refresh(ch)
        assert ch.status == "published"

    def test_skips_chapters_with_needs_review_lessons(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_draft_chapter(db_session, course.id)
        _seed_lesson(db_session, ch.id, status="published", content="ok")
        _seed_lesson(db_session, ch.id, status="needs_review", content="problem")

        resp = client.post(f"/api/courses/{course.id}/publish")
        assert resp.status_code == 200
        body = resp.json()
        assert body["published_chapters"] == 0
        assert body["skipped_chapters"] == 1

    def test_404_when_course_not_found(self, client, db_session):
        resp = client.post("/api/courses/nonexistent/publish")
        assert resp.status_code == 404

    def test_empty_result_when_no_draft_chapters(self, client, db_session):
        course = _seed_course(db_session)
        resp = client.post(f"/api/courses/{course.id}/publish")
        assert resp.status_code == 200
        body = resp.json()
        assert body["published_chapters"] == 0
        assert body["published_lessons"] == 0
        assert body["skipped_chapters"] == 0


# ---------------------------------------------------------------------------
# GET /lessons/{id}/content
# ---------------------------------------------------------------------------

class TestGetLessonContent:
    def test_returns_lesson_content(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_draft_chapter(db_session, course.id)
        _seed_parent(db_session, "p1", course.id)
        ls = _seed_lesson(
            db_session, ch.id,
            source_refs=["p1"],
            status="published",
            content="## Bitcoin\n\nBitcoin is a currency.",
        )

        resp = client.get(f"/api/lessons/{ls.id}/content")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == ls.id
        assert body["title"] == "Lesson 1"
        assert "Bitcoin" in body["content"]
        assert body["status"] == "published"
        assert body["source_refs"] == ["p1"]
        assert body["quiz"] is None

    def test_returns_quiz_when_present(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_draft_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, status="published", content="content")

        quiz = Quiz(
            id=str(uuid.uuid4()),
            scope=QuizScope.LESSON,
            title="Quiz: Lesson 1",
            passing_score=70,
            lesson_id=ls.id,
        )
        db_session.add(quiz)
        db_session.flush()
        q = Question(
            id=str(uuid.uuid4()),
            quiz_id=quiz.id,
            qtype=QuestionType.MCQ,
            prompt="What is Bitcoin?",
            order_index=0,
        )
        db_session.add(q)
        db_session.flush()
        for key in ["A", "B", "C", "D"]:
            db_session.add(OptionChoice(
                id=str(uuid.uuid4()),
                question_id=q.id,
                label=f"{key}) Option {key}",
                is_correct=(key == "A"),
            ))
        db_session.commit()

        resp = client.get(f"/api/lessons/{ls.id}/content")
        assert resp.status_code == 200
        body = resp.json()
        assert body["quiz"] is not None
        assert body["quiz"]["id"] == quiz.id
        assert len(body["quiz"]["questions"]) == 1
        assert len(body["quiz"]["questions"][0]["options"]) == 4
        # Student-facing endpoint must never leak the correct answer.
        for opt in body["quiz"]["questions"][0]["options"]:
            assert "is_correct" not in opt

    def test_404_when_lesson_not_found(self, client, db_session):
        resp = client.get("/api/lessons/nonexistent-lesson/content")
        assert resp.status_code == 404

    def test_empty_source_refs_when_none(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_draft_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, source_refs=None, content="content")

        resp = client.get(f"/api/lessons/{ls.id}/content")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_refs"] == []
