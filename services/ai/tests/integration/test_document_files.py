"""Original files remain authenticated, available after ingest, and deletable."""
import uuid
from contextlib import contextmanager

import fitz
import pytest

from app.api import documents_api
from app.core.config import create_access_token
from app.db.models import CourseDocument, UserRole
from app.services import document_service
from app.workers import pipeline
from tests.conftest import make_course_with_lessons, make_user


@pytest.fixture
def ingested_pdf(db, tmp_path, monkeypatch):
    course, _ = make_course_with_lessons(db, n_lessons=1)
    doc_id = str(uuid.uuid4())
    upload_dir = tmp_path / course.id
    upload_dir.mkdir()
    path = upload_dir / f"{doc_id}_source.pdf"
    pdf = fitz.open()
    for number in (1, 2):
        page = pdf.new_page()
        page.insert_textbox(fitz.Rect(40, 40, 550, 700), (
            f"Section {number}: This synthetic lesson describes transaction validation, "
            "record storage and retrieval. Students compare these operations and explain "
            "why reliable records are important when several participants share information. "
        ) * 3)
    pdf.save(path)
    pdf.close()
    original = path.read_bytes()
    doc = CourseDocument(
        id=doc_id, course_id=course.id, filename="source.pdf",
        mime_type="application/pdf", size=len(original),
        status="processing", processing_stage="queued",
    )
    db.add(doc)
    db.commit()

    @contextmanager
    def isolated_db():
        yield db

    monkeypatch.setattr(pipeline, "get_db_context", isolated_db)
    monkeypatch.setattr(pipeline, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(documents_api, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "QVAC_INGEST_DIR", tmp_path / "index")
    monkeypatch.setattr(pipeline, "_qvac_ingest", lambda *args, **kwargs: "indexed")
    monkeypatch.setattr(pipeline, "_RAG_CONTEXTUAL_CHUNKS", False)
    monkeypatch.setattr(document_service, "_qvac_delete_workspace_chunks", lambda *args: None)
    pipeline.run(document_id=doc_id, course_id=course.id,
                 filename="source.pdf", file_path=str(path))
    db.refresh(doc)
    assert doc.status == "ready"
    assert doc.chunk_count > 0
    assert doc.page_count == 2
    user = make_user(db, UserRole.ADMIN)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.email, 'admin')}"}
    return doc_id, path, original, headers


def test_original_pdf_is_available_after_ingestion(client, ingested_pdf):
    doc_id, path, original, headers = ingested_pdf
    response = client.get(f"/api/documents/{doc_id}/file", headers=headers)
    assert response.status_code == 200
    assert response.content == original
    assert path.exists()
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    # Fetching a blob for rendering does not require relaxing API frame protection.
    assert response.headers["x-frame-options"] == "DENY"


def test_original_pdf_requires_authentication(client, ingested_pdf):
    doc_id, _, _, _ = ingested_pdf
    assert client.get(f"/api/documents/{doc_id}/file").status_code == 401


def test_missing_original_explains_recovery(client, ingested_pdf):
    doc_id, path, _, headers = ingested_pdf
    path.unlink(missing_ok=True)
    response = client.get(f"/api/documents/{doc_id}/file", headers=headers)
    assert response.status_code == 404
    assert "re-upload" in response.json()["error"]["message"].lower()


def test_deleting_document_removes_retained_original(client, ingested_pdf):
    doc_id, path, _, headers = ingested_pdf
    assert path.exists()
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 200
    assert not path.exists()
    assert client.get(f"/api/documents/{doc_id}/file", headers=headers).status_code == 404
