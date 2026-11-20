"""Role checks on the endpoints that change course material.

Uploading, re-ingesting and deleting documents (and re-indexing a whole course)
is instructor/admin only, like course create/update/delete. Students keep read
access to the material: listing, status, detail, preview, structure and file.
"""
import uuid
from unittest.mock import patch

import pytest

from app.api import documents_api
from app.core.config import create_access_token
from app.db.models import CourseDocument, UserRole
from app.services import document_service
from app.workers import pipeline
from tests.conftest import make_course_with_lessons, make_user

_WRITERS = [UserRole.INSTRUCTOR, UserRole.ADMIN]


def _headers(db, role: UserRole) -> dict:
    user = make_user(db, role)
    token = create_access_token(user.id, user.email, role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def stored_document(db, tmp_path, monkeypatch):
    """A document whose upload file and QVAC contingency index exist on disk,
    so retry and reindex can succeed once authorization passes."""
    course, _ = make_course_with_lessons(db, n_lessons=1)
    doc_id = str(uuid.uuid4())
    (tmp_path / course.id).mkdir()
    (tmp_path / course.id / f"{doc_id}_source.pdf").write_bytes(b"%PDF-1.4 test")
    (tmp_path / "index").mkdir()
    (tmp_path / "index" / f"{doc_id}_contingency.jsonl").write_text("{}\n")
    db.add(CourseDocument(
        id=doc_id, course_id=course.id, filename="source.pdf",
        mime_type="application/pdf", size=13, status="ready",
    ))
    db.commit()

    monkeypatch.setattr(documents_api, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "QVAC_INGEST_DIR", tmp_path / "index")
    monkeypatch.setattr(document_service, "_qvac_delete_workspace_chunks", lambda *args: None)
    return course.id, doc_id


def _upload(client, course_id, headers):
    return client.post(
        f"/api/courses/{course_id}/documents",
        headers=headers,
        files={"file": ("notes.pdf", b"%PDF-1.4 test", "application/pdf")},
    )


_WRITE_CALLS = {
    "upload": lambda client, course_id, doc_id, headers: _upload(client, course_id, headers),
    "reindex_document": lambda client, course_id, doc_id, headers: client.post(
        f"/api/documents/{doc_id}/reindex", headers=headers),
    "retry_document": lambda client, course_id, doc_id, headers: client.post(
        f"/api/documents/{doc_id}/retry", headers=headers),
    "delete_document": lambda client, course_id, doc_id, headers: client.delete(
        f"/api/documents/{doc_id}", headers=headers),
    "reindex_course": lambda client, course_id, doc_id, headers: client.post(
        f"/api/courses/{course_id}/reindex", headers=headers),
}

_EXPECTED_SUCCESS = {
    "upload": 201,
    "reindex_document": 200,
    "retry_document": 200,
    "delete_document": 200,
    "reindex_course": 200,
}


@pytest.mark.integration
@pytest.mark.parametrize("action", sorted(_WRITE_CALLS))
def test_student_cannot_change_course_material(client, db, stored_document, action):
    course_id, doc_id = stored_document
    with patch("app.workers.pipeline.run"), patch("app.workers.pipeline.reindex_qvac"):
        resp = _WRITE_CALLS[action](client, course_id, doc_id, _headers(db, UserRole.STUDENT))
    assert resp.status_code == 403

    db.expire_all()
    docs = db.query(CourseDocument).filter(CourseDocument.course_id == course_id).all()
    assert [d.id for d in docs] == [doc_id]
    assert docs[0].status == "ready"


@pytest.mark.integration
@pytest.mark.parametrize("role", _WRITERS, ids=lambda r: r.value)
@pytest.mark.parametrize("action", sorted(_WRITE_CALLS))
def test_instructor_and_admin_can_change_course_material(
    client, db, stored_document, action, role
):
    course_id, doc_id = stored_document
    with patch("app.workers.pipeline.run"), patch("app.workers.pipeline.reindex_qvac"):
        resp = _WRITE_CALLS[action](client, course_id, doc_id, _headers(db, role))
    assert resp.status_code == _EXPECTED_SUCCESS[action], resp.text


@pytest.mark.integration
@pytest.mark.parametrize("path", [
    "/api/courses/{course_id}/documents",
    "/api/documents/{doc_id}",
    "/api/documents/{doc_id}/status",
    "/api/documents/{doc_id}/file",
])
def test_student_keeps_read_access(client, db, stored_document, path):
    course_id, doc_id = stored_document
    resp = client.get(
        path.format(course_id=course_id, doc_id=doc_id),
        headers=_headers(db, UserRole.STUDENT),
    )
    assert resp.status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize("action", sorted(_WRITE_CALLS))
def test_revoked_writer_token_cannot_change_course_material(
    client, db, stored_document, action, monkeypatch
):
    course_id, doc_id = stored_document
    headers = _headers(db, UserRole.INSTRUCTOR)
    token = headers["Authorization"].removeprefix("Bearer ")
    monkeypatch.setattr(
        "app.middleware.auth.is_token_blacklisted", lambda token_id: token_id == token[:32]
    )

    with patch("app.workers.pipeline.run") as run, patch(
        "app.workers.pipeline.reindex_qvac"
    ) as reindex:
        resp = _WRITE_CALLS[action](client, course_id, doc_id, headers)
    assert resp.status_code == 401
    run.assert_not_called()
    reindex.assert_not_called()
    db.expire_all()
    docs = db.query(CourseDocument).filter(CourseDocument.course_id == course_id).all()
    assert [doc.id for doc in docs] == [doc_id]
    assert docs[0].status == "ready"
