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
from tests.conftest import make_course_with_lessons


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

@pytest.mark.integration
def test_get_outline_empty(client, db):
    course, _ = make_course_with_lessons(db)

    resp = client.get(f"/api/courses/{course.id}/outline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["course_id"] == course.id
    assert body["chapters"] == []


# ---------------------------------------------------------------------------
# GET /api/courses/{id}/outline — with draft chapters
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_outline_returns_draft_chapters(client, db):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.get(f"/api/courses/{course.id}/outline")
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
def test_get_outline_unknown_course_404(client, db):
    resp = client.get(f"/api/courses/{uuid.uuid4()}/outline")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/courses/{id}/outline/generate
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_generate_outline_enqueues_and_returns_run_id(client, db):
    course, _ = make_course_with_lessons(db)
    _make_ready_doc(db, course.id)

    # BackgroundTasks will try to call generate_outline; patch it out.
    with patch(
        "app.api.outline_api._run_outline_bg", new_callable=AsyncMock
    ) as mock_bg:
        resp = client.post(
            f"/api/courses/{course.id}/outline/generate",
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
def test_generate_outline_no_ready_docs_422(client, db):
    course, _ = make_course_with_lessons(db)
    # no documents at all

    resp = client.post(f"/api/courses/{course.id}/outline/generate", json={})
    assert resp.status_code == 422


@pytest.mark.integration
def test_generate_outline_unknown_course_404(client, db):
    resp = client.post(
        f"/api/courses/{uuid.uuid4()}/outline/generate", json={}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/courses/{id}/outline — rename
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_patch_outline_renames_chapter(client, db):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
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
def test_patch_outline_reorders_chapters(client, db):
    course, _ = make_course_with_lessons(db)
    ch0, _ = _make_draft_chapter(db, course.id, title="Chapter A", order_index=0)
    ch1, _ = _make_draft_chapter(db, course.id, title="Chapter B", order_index=1)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
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
def test_patch_outline_deletes_chapter(client, db):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
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
def test_patch_outline_deletes_lesson(client, db):
    course, _ = make_course_with_lessons(db)
    chapter, lesson = _make_draft_chapter(db, course.id)

    resp = client.patch(
        f"/api/courses/{course.id}/outline",
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
def test_get_generation_run_returns_status(client, db):
    course, _ = make_course_with_lessons(db)
    run = _make_run(db, course.id, status=GenerationRunStatus.DONE)

    resp = client.get(f"/api/generation-runs/{run.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == run.id
    assert body["status"] == GenerationRunStatus.DONE
    assert body["course_id"] == course.id


@pytest.mark.integration
def test_get_generation_run_unknown_404(client, db):
    resp = client.get(f"/api/generation-runs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.integration
def test_get_generation_run_running_has_stage(client, db):
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

    resp = client.get(f"/api/generation-runs/{run.id}")
    assert resp.status_code == 200
    assert resp.json()["stage"] == "map_1/2"
