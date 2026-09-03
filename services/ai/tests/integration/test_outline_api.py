"""Integration tests for outline API endpoints (Phase 2).

POST   /api/courses/{id}/outline/generate
GET    /api/courses/{id}/outline
PATCH  /api/courses/{id}/outline
GET    /api/generation-runs/{run_id}

Uses the in-memory SQLite fixtures from conftest. LLM calls are mocked so no
real QVAC service is needed.
"""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import (
    Chapter,
    ChunkParent,
    CourseDocument,
    DocumentStatus,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
)
from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user
from app.db.models import Quiz, QuizScope, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ready_doc(db, course_id, tree=None):
    doc = CourseDocument(
        id=str(uuid.uuid4()),
        course_id=course_id,
        filename="test.pdf",
        size=1000,
        status=DocumentStatus.READY,
        section_tree_json=json.dumps(tree) if tree is not None else None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _make_run(db, course_id, status=GenerationRunStatus.DONE):
    run = GenerationRun(
        id=str(uuid.uuid4()),
        course_id=course_id,
        doc_ids_json=json.dumps([]),
        status=status,
        prompt_version="v1",
        created_at="2026-01-01T00:00:00",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _make_draft_chapter(db, course_id, title="Draft Chapter", order_index=0):
    chapter = Chapter(
        id=str(uuid.uuid4()),
        course_id=course_id,
        title=title,
        order_index=order_index,
        status="draft",
    )
    db.add(chapter)
    db.flush()
    lesson = Lesson(
        id=str(uuid.uuid4()),
        chapter_id=chapter.id,
        title="Draft Lesson",
        content="",
        order_index=0,
        status="draft",
        source_refs_json=json.dumps(["chunk1"]),
    )
    db.add(lesson)
    db.commit()
    db.refresh(chapter)
    db.refresh(lesson)
    return chapter, lesson


# ---------------------------------------------------------------------------
# GET /api/courses/{id}/outline — empty
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_headers(db) -> dict:
    """These endpoints require authentication."""
    user = make_user(db)
    role = getattr(user.role, "value", user.role)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, role)}"}


@pytest.fixture
def reviewer_headers(db) -> dict:
    user = make_user(db, role=UserRole.INSTRUCTOR)
    role = getattr(user.role, "value", user.role)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, role)}"}


@pytest.mark.integration
def test_get_outline_empty(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)

    resp = client.get(f"/api/courses/{course.id}/outline", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["course_id"] == course.id
    assert body["chapters"] == []


# ---------------------------------------------------------------------------
# GET /api/courses/{id}/outline — with draft chapters
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_outline_returns_draft_chapters(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.get(f"/api/courses/{course.id}/outline", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["chapters"]) == 1
    assert body["chapters"][0]["title"] == "Draft Chapter"
    assert body["chapters"][0]["status"] == "draft"
    assert len(body["chapters"][0]["lessons"]) == 1
    assert body["chapters"][0]["lessons"][0]["source_refs"] == ["chunk1"]


# ---------------------------------------------------------------------------
# GET /api/courses/{id}/outline — 404 for unknown course
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_outline_unknown_course_404(client, db, auth_headers):
    resp = client.get(f"/api/courses/{uuid.uuid4()}/outline", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/courses/{id}/outline/generate
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_generate_outline_enqueues_and_returns_run_id(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    _make_ready_doc(db, course.id)

    # BackgroundTasks will try to call generate_outline; patch it out.
    with patch(
        "app.api.outline_api._run_outline_bg", new_callable=AsyncMock
    ) as mock_bg:
        resp = client.post(
            f"/api/courses/{course.id}/outline/generate",
            headers=auth_headers,
            json={},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "run_id" in body
    assert body["status"] == GenerationRunStatus.QUEUED

    # GenerationRun persisted
    run = db.query(GenerationRun).filter(GenerationRun.id == body["run_id"]).first()
    assert run is not None
    assert run.course_id == course.id


@pytest.mark.integration
def test_generate_outline_no_ready_docs_422(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    # no documents at all

    resp = client.post(f"/api/courses/{course.id}/outline/generate", json={}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.integration
def test_generate_outline_unknown_course_404(client, db, auth_headers):
    resp = client.post(
        f"/api/courses/{uuid.uuid4()}/outline/generate", json={},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/courses/{id}/outline — rename
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_patch_outline_renames_chapter(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
        headers=auth_headers,
        json={
            "chapters": [
                {
                    "id": chapter.id,
                    "title": "Renamed Chapter",
                    "lessons": [
                        {"id": lesson.id, "title": "Renamed Lesson"}
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["chapters"][0]["title"] == "Renamed Chapter"
    assert body["chapters"][0]["lessons"][0]["title"] == "Renamed Lesson"


# ---------------------------------------------------------------------------
# PATCH /api/courses/{id}/outline — reorder
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_patch_outline_reorders_chapters(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    ch0, _ = _make_draft_chapter(db, course.id, title="Chapter A", order_index=0)
    ch1, _ = _make_draft_chapter(db, course.id, title="Chapter B", order_index=1)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
        headers=auth_headers,
        json={
            "chapters": [
                {"id": ch0.id, "order_index": 1, "lessons": []},
                {"id": ch1.id, "order_index": 0, "lessons": []},
            ]
        },
    )
    assert resp.status_code == 200

    db.refresh(ch0)
    db.refresh(ch1)
    assert ch0.order_index == 1
    assert ch1.order_index == 0


# ---------------------------------------------------------------------------
# PATCH /api/courses/{id}/outline — delete chapter
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_patch_outline_deletes_chapter(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
        headers=auth_headers,
        json={"chapters": [{"id": chapter.id, "delete": True, "lessons": []}]},
    )
    assert resp.status_code == 200
    assert resp.json()["chapters"] == []

    assert db.query(Chapter).filter(Chapter.id == chapter.id).first() is None
    assert db.query(Lesson).filter(Lesson.id == lesson.id).first() is None


# ---------------------------------------------------------------------------
# PATCH /api/courses/{id}/outline — delete lesson only
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_patch_outline_deletes_lesson(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
        headers=auth_headers,
        json={
            "chapters": [
                {
                    "id": chapter.id,
                    "lessons": [{"id": lesson.id, "delete": True}],
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert db.query(Lesson).filter(Lesson.id == lesson.id).first() is None
    # Chapter still exists
    assert db.query(Chapter).filter(Chapter.id == chapter.id).first() is not None


# ---------------------------------------------------------------------------
# GET /api/generation-runs/{run_id}
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_generation_run_returns_status(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    run = _make_run(db, course.id, status=GenerationRunStatus.DONE)

    resp = client.get(f"/api/generation-runs/{run.id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == run.id
    assert body["status"] == GenerationRunStatus.DONE
    assert body["course_id"] == course.id


@pytest.mark.integration
def test_get_generation_run_unknown_404(client, db, auth_headers):
    resp = client.get(f"/api/generation-runs/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.integration
def test_get_generation_run_running_has_stage(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    run = GenerationRun(
        id=str(uuid.uuid4()),
        course_id=course.id,
        doc_ids_json=json.dumps([]),
        status=GenerationRunStatus.RUNNING,
        stage="map_1/2",
        prompt_version="v1",
        created_at="2026-01-01T00:00:00",
    )
    db.add(run)
    db.commit()

    resp = client.get(f"/api/generation-runs/{run.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["stage"] == "map_1/2"


# ---------------------------------------------------------------------------
# POST /api/courses/{id}/outline/actions — manual restructuring
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_outline_actions_require_reviewer(client, db, auth_headers):
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/outline/actions",
        headers=auth_headers,
        json={"action": "create_chapter", "title": "Manual"},
    )
    assert resp.status_code == 403


@pytest.mark.integration
def test_create_and_rename_items_marks_human_provenance(client, db, reviewer_headers):
    course, _ = make_course_with_lessons(db)
    created = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "create_chapter", "title": "Manual chapter"},
    )
    assert created.status_code == 200
    chapter = created.json()["chapters"][-1]
    assert chapter["is_human_modified"] is True
    assert chapter["human_modified_at"]

    renamed_chapter = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "rename_chapter", "chapter_id": chapter["id"], "title": "Renamed chapter"},
    )
    assert renamed_chapter.json()["chapters"][-1]["title"] == "Renamed chapter"

    lesson_resp = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "create_lesson", "chapter_id": chapter["id"], "title": "Manual lesson"},
    )
    lesson = lesson_resp.json()["chapters"][-1]["lessons"][0]
    renamed = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "rename_lesson", "lesson_id": lesson["id"], "title": "Renamed"},
    )
    assert renamed.json()["chapters"][-1]["lessons"][0]["title"] == "Renamed"
    assert renamed.json()["chapters"][-1]["lessons"][0]["is_human_modified"] is True

    chapter_ids = [item["id"] for item in renamed.json()["chapters"]]
    reordered = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "reorder_chapters", "ordered_ids": list(reversed(chapter_ids))},
    )
    assert [item["id"] for item in reordered.json()["chapters"]] == list(reversed(chapter_ids))

    deleted = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "delete_lesson", "lesson_id": lesson["id"]},
    )
    assert all(not item["lessons"] for item in deleted.json()["chapters"] if item["id"] == chapter["id"])


@pytest.mark.integration
def test_reorder_and_move_lesson_preserve_content_quiz_and_sources(client, db, reviewer_headers):
    course, lessons = make_course_with_lessons(db)
    source = lessons[0].chapter
    source.status = "draft"
    lessons[0].source_refs_json = json.dumps(["source-1"])
    quiz = Quiz(id=str(uuid.uuid4()), scope=QuizScope.LESSON, lesson_id=lessons[0].id, title="Quiz")
    target = Chapter(id=str(uuid.uuid4()), course_id=course.id, title="Target", order_index=1, status="draft")
    db.add_all([quiz, target])
    db.commit()

    reordered = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "reorder_lessons", "chapter_id": source.id,
              "ordered_ids": [lessons[1].id, lessons[0].id]},
    )
    assert reordered.status_code == 200
    moved = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "move_lesson", "lesson_id": lessons[0].id, "target_chapter_id": target.id},
    )
    assert moved.status_code == 200
    db.expire_all()
    lesson = db.query(Lesson).filter_by(id=lessons[0].id).one()
    assert lesson.chapter_id == target.id
    assert lesson.content == "Content."
    assert lesson.source_refs_json == json.dumps(["source-1"])
    assert db.query(Quiz).filter_by(id=quiz.id, lesson_id=lesson.id).one()


@pytest.mark.integration
def test_merge_and_split_chapters_move_existing_lessons(client, db, reviewer_headers):
    course, lessons = make_course_with_lessons(db)
    source = lessons[0].chapter
    source.status = "draft"
    target, target_lesson = _make_draft_chapter(db, course.id, "Target", 1)
    merged = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "merge_chapters", "chapter_id": source.id, "target_chapter_id": target.id},
    )
    assert merged.status_code == 200
    moved_ids = [item["id"] for item in merged.json()["chapters"][0]["lessons"]]
    assert set(moved_ids) == {target_lesson.id, lessons[0].id, lessons[1].id}

    split = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "split_chapter", "chapter_id": target.id, "title": "Split",
              "lesson_ids": [lessons[1].id]},
    )
    assert split.status_code == 200
    assert [chapter["title"] for chapter in split.json()["chapters"]] == ["Target", "Split"]
    assert split.json()["chapters"][1]["lessons"][0]["id"] == lessons[1].id


@pytest.mark.integration
def test_delete_chapter_with_lessons_requires_explicit_choice(client, db, reviewer_headers):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)
    quiz = Quiz(id=str(uuid.uuid4()), scope=QuizScope.LESSON, lesson_id=lesson.id, title="Generated")
    db.add(quiz)
    db.commit()
    lesson_id = lesson.id
    quiz_id = quiz.id
    rejected = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "delete_chapter", "chapter_id": chapter.id},
    )
    assert rejected.status_code == 422
    confirmed = client.post(
        f"/api/courses/{course.id}/outline/actions", headers=reviewer_headers,
        json={"action": "delete_chapter", "chapter_id": chapter.id, "delete_lessons": True},
    )
    assert confirmed.status_code == 200
    assert db.query(Lesson).filter_by(id=lesson_id).first() is None
    assert db.query(Quiz).filter_by(id=quiz_id).first() is None
