"""Integration tests for the P2 review-UI backend: PATCH lesson, approve,
and regenerate-by-lesson_ids. Same self-contained fixture pattern as
test_content_api.py (own in-memory engine, no lifespan trigger).
"""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import create_access_token
from app.db.models import Base, Chapter, Course, GenerationRun, Lesson, Section
from app.db.session import get_db
from app.main import app


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
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    app.state.arq_pool = None
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.pop(get_db, None)


def _auth(role: str = "instructor") -> dict:
    token = create_access_token(str(uuid.uuid4()), "reviewer@test.com", role)
    return {"Authorization": f"Bearer {token}"}


def _seed_course(db):
    section = Section(id=str(uuid.uuid4()), title="Test")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), title="Test Course", section_id=section.id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _seed_chapter(db, course_id, status="draft"):
    ch = Chapter(id=str(uuid.uuid4()), course_id=course_id, title="Ch1", order_index=0, status=status)
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


class TestStudentLessonVisibility:
    def test_course_list_contains_only_published_lessons(self, client, db_session):
        course = _seed_course(db_session)
        chapter = _seed_chapter(db_session, course.id)
        published = _seed_lesson(db_session, chapter.id, status="published", content="Ready")
        _seed_lesson(db_session, chapter.id, status="draft", content="Not ready")

        response = client.get(
            f"/api/courses/{course.id}/lessons", headers=_auth("student")
        )

        assert response.status_code == 200
        assert [lesson["id"] for lesson in response.json()] == [published.id]

    def test_draft_lesson_is_not_accessible_directly(self, client, db_session):
        course = _seed_course(db_session)
        chapter = _seed_chapter(db_session, course.id)
        draft = _seed_lesson(db_session, chapter.id, status="draft", content="Not ready")

        response = client.get(f"/api/lessons/{draft.id}", headers=_auth("student"))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /lessons/{id}
# ---------------------------------------------------------------------------

class TestPatchLesson:
    def test_requires_auth(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, content="Original")

        resp = client.patch(f"/api/lessons/{ls.id}", json={"title": "New title"})
        assert resp.status_code == 401

    def test_rejects_student_role(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, content="Original")

        resp = client.patch(
            f"/api/lessons/{ls.id}", json={"title": "New title"}, headers=_auth("student"),
        )
        assert resp.status_code == 403

    def test_updates_title_and_description(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, content="Original content")

        resp = client.patch(
            f"/api/lessons/{ls.id}",
            json={"title": "Better Title", "description": "Better desc"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Better Title"
        assert body["description"] == "Better desc"
        assert body["content"] == "Original content"  # untouched

    def test_updates_content_and_recomputes_hash(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, source_refs=["p1"], content="Old content")

        resp = client.patch(
            f"/api/lessons/{ls.id}",
            json={"content": "Rewritten by instructor."},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "Rewritten by instructor."

        db_session.refresh(ls)
        assert ls.content == "Rewritten by instructor."
        assert ls.content_hash is not None

        from app.services.lesson_service import compute_content_hash
        assert ls.content_hash == compute_content_hash(ls)

    def test_edit_strips_groundedness_issues_comment(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        content_with_issues = (
            "Some content.\n\n<!-- groundedness_issues:\n- Claim X unsupported\n-->"
        )
        ls = _seed_lesson(db_session, ch.id, content=content_with_issues, status="needs_review")

        # Verify the GET endpoint surfaces the issue before the edit
        pre_resp = client.get(f"/api/lessons/{ls.id}/content", headers=_auth())
        assert pre_resp.json()["review_issues"] == ["Claim X unsupported"]

        resp = client.patch(
            f"/api/lessons/{ls.id}",
            json={"content": "Fixed content, no issues."},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["review_issues"] == []
        assert "groundedness_issues" not in resp.json()["content"]

    def test_404_for_unknown_lesson(self, client, db_session):
        resp = client.patch(
            "/api/lessons/nonexistent-lesson-id", json={"title": "X"}, headers=_auth(),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /lessons/{id}/approve
# ---------------------------------------------------------------------------

class TestApproveLesson:
    def test_requires_auth(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, content="Some content", status="needs_review")

        resp = client.post(f"/api/lessons/{ls.id}/approve")
        assert resp.status_code == 401

    def test_rejects_student_role(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, content="Some content", status="needs_review")

        resp = client.post(f"/api/lessons/{ls.id}/approve", headers=_auth("student"))
        assert resp.status_code == 403

    def test_approves_needs_review_lesson(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, content="Reviewed content", status="needs_review")

        resp = client.post(f"/api/lessons/{ls.id}/approve", headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

        db_session.refresh(ls)
        assert ls.status == "published"

    def test_rejects_approval_with_no_content(self, client, db_session):
        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id)
        ls = _seed_lesson(db_session, ch.id, content="", status="draft")

        resp = client.post(f"/api/lessons/{ls.id}/approve", headers=_auth())
        assert resp.status_code == 422

    def test_404_for_unknown_lesson(self, client, db_session):
        resp = client.post("/api/lessons/nonexistent-lesson-id/approve", headers=_auth())
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /courses/{id}/content/generate with lesson_ids (regeneration)
# ---------------------------------------------------------------------------

class TestRegenerateSpecificLessons:
    def test_generate_with_lesson_ids_targets_only_those_lessons(self, client, db_session):
        course = _seed_course(db_session)
        # Published chapter — normally excluded from draft-only generation,
        # but lesson_ids should still target it explicitly.
        ch = _seed_chapter(db_session, course.id, status="published")
        ls1 = _seed_lesson(db_session, ch.id, source_refs=["p1"], content="Old", status="published")
        ls2 = _seed_lesson(db_session, ch.id, source_refs=["p2"], content="Old2", status="published")

        with patch(
            "app.api.content_api._run_content_bg", new_callable=AsyncMock
        ) as mock_bg:
            resp = client.post(
                f"/api/courses/{course.id}/content/generate",
                json={"lesson_ids": [ls1.id]},
                headers=_auth(),
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["draft_lessons"] == 1

        mock_bg.assert_called_once()
        args = mock_bg.call_args.args
        assert args[0] == course.id
        assert args[2] == [ls1.id]

    def test_generate_with_lesson_ids_422_when_none_belong_to_course(self, client, db_session):
        course = _seed_course(db_session)
        resp = client.post(
            f"/api/courses/{course.id}/content/generate",
            json={"lesson_ids": ["nonexistent-lesson"]},
            headers=_auth(),
        )
        assert resp.status_code == 422

    def test_regenerate_clears_cache_and_forces_reprocessing(self, db_session):
        """Unit-level check on the service the API delegates to: lesson_ids
        clears content_hash so process_lesson doesn't cache-hit-skip."""
        import asyncio
        from unittest.mock import AsyncMock as _AsyncMock

        from app.db.models import ChunkParent, GenerationRun, GenerationRunStatus
        from app.services import lesson_service
        from app.services.lesson_service import compute_content_hash

        course = _seed_course(db_session)
        ch = _seed_chapter(db_session, course.id, status="published")
        chunk = ChunkParent(id="p1", doc_id="d1", course_id=course.id, text="Bitcoin content.")
        db_session.add(chunk)
        ls = _seed_lesson(db_session, ch.id, source_refs=["p1"], content="Old", status="published")
        ls.content_hash = compute_content_hash(ls)  # simulate a cache hit if untouched
        db_session.commit()

        run = GenerationRun(
            id=str(uuid.uuid4()), course_id=course.id, doc_ids_json="[]",
            status=GenerationRunStatus.QUEUED,
        )
        db_session.add(run)
        db_session.commit()

        content_result = {
            "content": "New content.", "objectives": ["Obj"], "glossary": [], "self_check": ["Q1", "Q2"],
        }
        judge_result = {"faithful": True, "issues": []}

        with patch(
            "app.services.lesson_service.generate_json", new_callable=_AsyncMock
        ) as mock_gj, patch(
            "app.services.quiz_generation.generate_json", new_callable=_AsyncMock
        ) as mock_quiz_gj:
            mock_gj.side_effect = [content_result, judge_result]
            mock_quiz_gj.return_value = None
            asyncio.run(
                lesson_service.generate_course_content(
                    course_id=course.id, db=db_session, run_id=run.id, lesson_ids=[ls.id],
                )
            )

        db_session.refresh(ls)
        assert "New content." in ls.content
        assert ls.status == "published"
