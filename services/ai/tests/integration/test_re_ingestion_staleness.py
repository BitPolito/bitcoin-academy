"""Integration tests for issue #165 — re-ingestion behaviour that preserves
human edits.

app.services.outline_staleness_service already implements the staleness
model and is unit-tested directly (tests/unit/test_outline_staleness_service.py).
What's missing is coverage that the actual trigger points — the document
delete and retry *endpoints*, not the service function called in isolation —
wire up to it correctly. These tests exercise the real HTTP layer.
"""
import json
import uuid
from unittest.mock import patch

import pytest

from app.api import documents_api
from app.core.config import create_access_token
from app.db.models import Chapter, ChunkParent, Course, CourseDocument, UserRole
from app.services import document_service
from app.services.outline_staleness_service import source_snapshot
from app.workers import pipeline
from tests.conftest import make_course_with_lessons, make_user


def _headers(db) -> dict:
    user = make_user(db, UserRole.INSTRUCTOR)
    token = create_access_token(user.id, user.email, UserRole.INSTRUCTOR.value)
    return {"Authorization": f"Bearer {token}"}


def _link_lesson_to_document(db, lesson, document_id: str, course_id: str, text="Source text."):
    """Give *lesson* a source chunk anchored in *document_id*, as the
    course-builder pipeline would after generating its content."""
    parent = ChunkParent(
        id=f"chunk-{uuid.uuid4()}", doc_id=document_id, course_id=course_id, text=text,
        citation_label="p1", citation_page=1, citation_section="Intro",
    )
    db.add(parent)
    db.flush()
    lesson.source_refs_json = json.dumps([parent.id])
    lesson.source_snapshot_json = json.dumps(source_snapshot(db, [parent.id]))
    db.commit()
    return parent


@pytest.fixture
def stored_document(db, tmp_path, monkeypatch):
    """A document whose upload file exists on disk, so retry can succeed."""
    course, lessons = make_course_with_lessons(db, n_lessons=2)
    doc_id = str(uuid.uuid4())
    (tmp_path / course.id).mkdir()
    (tmp_path / course.id / f"{doc_id}_source.pdf").write_bytes(b"%PDF-1.4 test")
    db.add(CourseDocument(
        id=doc_id, course_id=course.id, filename="source.pdf",
        mime_type="application/pdf", size=13, status="ready",
    ))
    db.commit()

    monkeypatch.setattr(documents_api, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(document_service, "_qvac_delete_workspace_chunks", lambda *args: None)
    return course, lessons, doc_id


@pytest.mark.integration
def test_deleting_a_document_marks_only_its_sourced_lesson_stale(db, client, stored_document):
    course, lessons, doc_id = stored_document
    sourced, other = lessons
    _link_lesson_to_document(db, sourced, doc_id, course.id)
    # A human-edited lesson must still be flagged — "preserves edits" means
    # its content is untouched, not that staleness is suppressed entirely.
    sourced.is_human_modified = True
    db.commit()

    resp = client.delete(f"/api/documents/{doc_id}", headers=_headers(db))
    assert resp.status_code == 200, resp.text

    db.refresh(sourced)
    db.refresh(other)
    db.refresh(sourced.chapter)
    db.refresh(course)

    assert sourced.is_stale is True
    assert "source.pdf" in (sourced.stale_reason or "")
    assert sourced.is_human_modified is True
    assert sourced.content == "Content."  # untouched

    assert other.is_stale is False, "A lesson not sourced from the deleted document must stay untouched"
    assert sourced.chapter.is_stale is True
    assert course.outline_stale is True


@pytest.mark.integration
def test_retrying_a_document_marks_its_sourced_lesson_stale(db, client, stored_document):
    """Reprocessing (e.g. a different parser, or a corrected parse) can change
    chunk ids under a document's existing lessons — the retry endpoint must
    flag them for review, the same as a delete would."""
    course, lessons, doc_id = stored_document
    sourced, _other = lessons
    _link_lesson_to_document(db, sourced, doc_id, course.id)

    with patch("app.workers.pipeline.run"):
        resp = client.post(f"/api/documents/{doc_id}/retry", headers=_headers(db))
    assert resp.status_code == 200, resp.text

    db.refresh(sourced)
    assert sourced.is_stale is True
    assert "reprocess" in (sourced.stale_reason or "").lower()


@pytest.mark.integration
def test_deleting_every_document_marks_the_whole_outline_stale(db, client, tmp_path, monkeypatch):
    """No special-casing exists for 'all documents deleted' — each delete is
    handled individually. This proves that's still sufficient: after every
    source document is gone, every sourced lesson and the course are stale."""
    course, lessons = make_course_with_lessons(db, n_lessons=2)
    monkeypatch.setattr(documents_api, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(document_service, "_qvac_delete_workspace_chunks", lambda *args: None)

    doc_ids = []
    for i, lesson in enumerate(lessons):
        doc_id = str(uuid.uuid4())
        (tmp_path / course.id).mkdir(exist_ok=True)
        (tmp_path / course.id / f"{doc_id}_doc{i}.pdf").write_bytes(b"%PDF-1.4 test")
        db.add(CourseDocument(
            id=doc_id, course_id=course.id, filename=f"doc{i}.pdf",
            mime_type="application/pdf", size=13, status="ready",
        ))
        db.commit()
        _link_lesson_to_document(db, lesson, doc_id, course.id)
        doc_ids.append(doc_id)

    headers = _headers(db)
    for doc_id in doc_ids:
        resp = client.delete(f"/api/documents/{doc_id}", headers=headers)
        assert resp.status_code == 200, resp.text

    for lesson in lessons:
        db.refresh(lesson)
        assert lesson.is_stale is True
    db.refresh(course)
    assert course.outline_stale is True


@pytest.mark.integration
def test_accepting_a_stale_lesson_clears_it_and_the_course_flag(db, client, stored_document):
    """Review UI's 'Accept' action (outline_api's accept_stale) must clear
    the lesson's staleness, and once nothing else is stale, the course-level
    flag too — otherwise the reviewer would never be able to dismiss the
    'Outline needs review' banner."""
    course, lessons, doc_id = stored_document
    sourced, _other = lessons
    _link_lesson_to_document(db, sourced, doc_id, course.id)

    headers = _headers(db)
    del_resp = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text

    db.refresh(sourced)
    assert sourced.is_stale is True
    db.refresh(course)
    assert course.outline_stale is True

    accept_resp = client.post(
        f"/api/courses/{course.id}/outline/actions",
        json={"action": "accept_stale", "lesson_id": sourced.id},
        headers=headers,
    )
    assert accept_resp.status_code == 200, accept_resp.text

    db.refresh(sourced)
    assert sourced.is_stale is False
    assert sourced.stale_reason is None
    db.refresh(course)
    assert course.outline_stale is False, (
        "No lesson is stale anymore — the course-level banner must clear too"
    )


@pytest.mark.integration
def test_regenerating_a_stale_human_edited_lesson_requires_confirmation(db, client, stored_document):
    """Targeted regeneration (content_api's lesson_ids path) must not
    silently discard a human edit, even when the lesson is also stale —
    staleness alone is not consent to overwrite."""
    course, lessons, doc_id = stored_document
    sourced, _other = lessons
    _link_lesson_to_document(db, sourced, doc_id, course.id)
    sourced.is_human_modified = True
    db.commit()

    headers = _headers(db)
    del_resp = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text
    db.refresh(sourced)
    assert sourced.is_stale is True
    assert sourced.is_human_modified is True

    with patch("app.api.content_api._run_content_bg") as mock_bg:
        refused = client.post(
            f"/api/courses/{course.id}/content/generate",
            json={"lesson_ids": [sourced.id]},
            headers=headers,
        )
    assert refused.status_code == 422, refused.text
    mock_bg.assert_not_called()

    with patch("app.api.content_api._run_content_bg") as mock_bg:
        confirmed = client.post(
            f"/api/courses/{course.id}/content/generate",
            json={"lesson_ids": [sourced.id], "confirm_human_overwrite": True},
            headers=headers,
        )
    assert confirmed.status_code == 202, confirmed.text
    mock_bg.assert_called_once()
