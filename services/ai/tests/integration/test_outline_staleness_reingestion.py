"""Integration coverage for outline staleness through the real document
lifecycle endpoints (issue #165): upload, delete, and reprocessing must each
flag the lessons that depend on the changed source, through the same code
paths a user actually exercises — not just the staleness helpers in
isolation (see tests/unit/test_outline_staleness_service.py).
"""
import json
from unittest.mock import patch

import pytest

from app.db.models import Chapter, ChunkParent, CourseDocument, UserRole
from app.services import document_service
from tests.conftest import make_course_with_lessons, make_user
from tests.integration.test_documents_api import _auth


@pytest.fixture
def auth_headers(db) -> dict:
    return _auth(make_user(db, UserRole.INSTRUCTOR).id, "instructor")


def _attach_source(db, lesson, document_id: str, chunk_id: str, text: str):
    """Give a lesson a real source chunk, as the outline pipeline would."""
    parent = ChunkParent(
        id=chunk_id, doc_id=document_id, course_id=lesson.chapter.course_id, text=text,
        citation_label="p1", citation_page=1, citation_section="Intro",
    )
    db.add(parent)
    db.flush()
    lesson.source_refs_json = json.dumps([chunk_id])
    from app.services.outline_staleness_service import source_snapshot
    lesson.source_snapshot_json = json.dumps(source_snapshot(db, [chunk_id]))
    db.commit()


@pytest.mark.integration
def test_upload_marks_existing_outline_stale(client, db, auth_headers):
    course, lessons = make_course_with_lessons(db)
    db.query(Chapter).filter(Chapter.course_id == course.id).update({"status": "published"})
    db.commit()

    with patch("app.workers.pipeline.run"):
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            headers=auth_headers,
            files={"file": ("new-material.pdf", b"%PDF fake", "application/pdf")},
        )
    assert resp.status_code == 201

    db.refresh(course)
    assert course.outline_stale is True
    assert "new-material.pdf" in course.outline_stale_reason


@pytest.mark.integration
def test_delete_document_flags_only_lessons_sourced_from_it(client, db, auth_headers):
    course, lessons = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run"):
        upload_resp = client.post(
            f"/api/courses/{course.id}/documents",
            headers=auth_headers,
            files={"file": ("sourced.pdf", b"%PDF fake", "application/pdf")},
        )
    doc_id = upload_resp.json()["id"]
    _attach_source(db, lessons[0], doc_id, "chunk-sourced", "This lesson's source text.")

    del_resp = client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    db.refresh(lessons[0])
    db.refresh(lessons[1])
    assert lessons[0].is_stale is True
    assert "sourced.pdf" in lessons[0].stale_reason
    assert "was deleted" in lessons[0].stale_reason
    assert lessons[1].is_stale is False

    # The chunk the lesson pointed at is actually gone — not just marked stale.
    assert db.query(ChunkParent).filter(ChunkParent.id == "chunk-sourced").first() is None


@pytest.mark.integration
def test_deleting_human_edited_lesson_source_preserves_its_content(client, db, auth_headers):
    """Staleness flags the lesson for review; it must never silently rewrite
    or discard a human-edited lesson's content on its own."""
    course, lessons = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run"):
        upload_resp = client.post(
            f"/api/courses/{course.id}/documents",
            headers=auth_headers,
            files={"file": ("sourced.pdf", b"%PDF fake", "application/pdf")},
        )
    doc_id = upload_resp.json()["id"]
    _attach_source(db, lessons[0], doc_id, "chunk-sourced", "Original text.")
    lessons[0].is_human_modified = True
    lessons[0].content = "The reviewer's corrected content."
    db.commit()

    client.delete(f"/api/documents/{doc_id}", headers=auth_headers)

    db.refresh(lessons[0])
    assert lessons[0].is_stale is True
    assert lessons[0].is_human_modified is True
    assert lessons[0].content == "The reviewer's corrected content."


@pytest.mark.integration
def test_deleting_every_document_in_a_course_flags_every_sourced_lesson(client, db, auth_headers):
    course, lessons = make_course_with_lessons(db)

    doc_ids = []
    with patch("app.workers.pipeline.run"):
        for i, lesson in enumerate(lessons):
            resp = client.post(
                f"/api/courses/{course.id}/documents",
                headers=auth_headers,
                files={"file": (f"doc-{i}.pdf", b"%PDF fake", "application/pdf")},
            )
            doc_id = resp.json()["id"]
            doc_ids.append(doc_id)
            _attach_source(db, lesson, doc_id, f"chunk-{i}", f"Text for lesson {i}.")

    for doc_id in doc_ids:
        resp = client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
        assert resp.status_code == 200

    for lesson in lessons:
        db.refresh(lesson)
        assert lesson.is_stale is True
    db.refresh(course)
    assert course.outline_stale is True


@pytest.mark.integration
def test_reprocessing_a_document_flags_its_lessons_as_stale(db):
    """A parser switch (USE_DOCLING toggled) can change chunk ids while the
    document row stays the same — reprocessing must always invalidate the
    lessons sourced from it, since staleness here is driven by the act of
    reprocessing, not by comparing old and new chunk ids up front."""
    course, lessons = make_course_with_lessons(db)
    document = CourseDocument(
        id="doc-reprocess", course_id=course.id, filename="reprocessed.pdf", size=10,
        status="error",
    )
    db.add(document)
    db.flush()
    _attach_source(db, lessons[0], document.id, "chunk-reprocess", "Text before reprocessing.")

    document_service.reset_status(db, document.id)

    db.refresh(lessons[0])
    assert lessons[0].is_stale is True
    assert "reprocessed" in lessons[0].stale_reason
