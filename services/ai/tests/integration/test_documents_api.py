"""Integration tests for the documents upload and management API.

POST /api/courses/{course_id}/documents — upload a file, trigger pipeline
GET  /api/courses/{course_id}/documents — list documents
GET  /api/documents/{id}/status         — polling status
GET  /api/documents/{id}                — detail
GET  /api/documents/{id}/preview        — preview
DELETE /api/documents/{id}              — soft-delete

The pipeline background task is patched so tests remain fast and deterministic.
Real file bytes from docs/src/ are used for the upload payload.
"""
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOCS = _REPO_ROOT / "docs" / "src"
PDF_PATH = _DOCS / "bitcoin_technical_document.pdf"
PPTX_PATH = _DOCS / "bitcoin_creative_commons_en.pptx"


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


def _skip_if_missing(path: Path):
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")


# ---------------------------------------------------------------------------
# List documents — no auth required per router definition
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_list_documents_empty_course(client, db):
    course, _ = make_course_with_lessons(db)
    resp = client.get(f"/api/courses/{course.id}/documents")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_list_documents_unknown_course_returns_empty(client, db):
    resp = client.get("/api/courses/nonexistent-course-id/documents")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Upload — POST /api/courses/{course_id}/documents
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_upload_pdf_returns_201(client, db):
    _skip_if_missing(PDF_PATH)
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run") as mock_run:
        mock_run.return_value = None
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("bitcoin_technical_document.pdf", PDF_PATH.read_bytes(), "application/pdf")},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "bitcoin_technical_document.pdf"
    assert "id" in data


@pytest.mark.integration
def test_upload_pptx_returns_201(client, db):
    _skip_if_missing(PPTX_PATH)
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run") as mock_run:
        mock_run.return_value = None
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": (
                "bitcoin_creative_commons_en.pptx",
                PPTX_PATH.read_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "bitcoin_creative_commons_en.pptx"


@pytest.mark.integration
def test_upload_creates_document_record(client, db):
    _skip_if_missing(PDF_PATH)
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run"):
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("test.pdf", PDF_PATH.read_bytes(), "application/pdf")},
        )

    doc_id = resp.json()["id"]

    list_resp = client.get(f"/api/courses/{course.id}/documents")
    assert list_resp.status_code == 200
    ids = [d["id"] for d in list_resp.json()]
    assert doc_id in ids


@pytest.mark.integration
def test_upload_triggers_pipeline_background_task(client, db):
    _skip_if_missing(PDF_PATH)
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run") as mock_run:
        mock_run.return_value = None
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("test.pdf", PDF_PATH.read_bytes(), "application/pdf")},
        )

    assert resp.status_code == 201
    # TestClient runs background tasks synchronously
    assert mock_run.called
    call_kwargs = mock_run.call_args[1] if mock_run.call_args[1] else {}
    call_args = mock_run.call_args[0] if mock_run.call_args[0] else ()
    # Either positional or keyword — just verify doc_id and course_id are present
    all_args = {**{str(i): v for i, v in enumerate(call_args)}, **call_kwargs}
    assert course.id in str(all_args)


@pytest.mark.integration
def test_upload_tiny_file(client, db):
    """Upload a minimal valid payload (in-memory bytes, not a real file)."""
    course, _ = make_course_with_lessons(db)
    fake_content = b"%PDF-1.4 fake pdf content"

    with patch("app.workers.pipeline.run"):
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("tiny.pdf", io.BytesIO(fake_content), "application/pdf")},
        )

    assert resp.status_code == 201
    assert resp.json()["filename"] == "tiny.pdf"


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_document_status_after_upload(client, db):
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run"):
        upload_resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("test.pdf", b"%PDF fake", "application/pdf")},
        )

    doc_id = upload_resp.json()["id"]
    status_resp = client.get(f"/api/documents/{doc_id}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "status" in data
    assert "id" in data


@pytest.mark.integration
def test_get_document_status_unknown_id_returns_404(client, db):
    resp = client.get("/api/documents/nonexistent-doc-id/status")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Document detail
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_document_detail_after_upload(client, db):
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run"):
        upload_resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("test.pdf", b"%PDF fake", "application/pdf")},
        )

    doc_id = upload_resp.json()["id"]
    detail_resp = client.get(f"/api/documents/{doc_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == doc_id


@pytest.mark.integration
def test_get_document_detail_unknown_returns_404(client, db):
    resp = client.get("/api/documents/does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_delete_document(client, db):
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run"):
        upload_resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("test.pdf", b"%PDF fake", "application/pdf")},
        )

    doc_id = upload_resp.json()["id"]
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200

    # Should now be absent from list
    list_resp = client.get(f"/api/courses/{course.id}/documents")
    ids = [d["id"] for d in list_resp.json()]
    assert doc_id not in ids


@pytest.mark.integration
def test_delete_nonexistent_returns_404(client, db):
    resp = client.delete("/api/documents/nonexistent-id")
    assert resp.status_code == 404
