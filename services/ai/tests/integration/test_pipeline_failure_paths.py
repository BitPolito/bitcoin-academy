"""Ingestion failure paths — corrupt files, empty files, unsupported types, size limits.

The one property that matters across all of these: a document must never be
left in `processing` forever. The README documents exactly that symptom as a
known troubleshooting entry (worker not consuming a queued job); this file
covers the other half — failures inside the pipeline itself must always reach
a terminal, inspectable state (`ERROR` with a message, or `READY` with an
honest zero chunk count), never silently hang.

Uses the same `_run_pipeline` harness as test_pipeline_e2e.py: QVAC ingest is
patched out, so none of this requires QVAC, Redis, or the ARQ worker running.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import gc 
from tests.conftest import make_course_with_lessons, make_user
from tests.integration.test_pipeline_e2e import _run_pipeline


def _write_temp(suffix: str, content: bytes) -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        return Path(f.name)


# ---------------------------------------------------------------------------
# Pipeline-level failures — app.workers.pipeline.run()
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_unsupported_extension_marks_error_not_stuck(db):
    """pipeline.run() has its own extension check independent of the upload
    endpoint's MIME-type check — a defence-in-depth path exercised here."""
    course, _ = make_course_with_lessons(db)
    path = _write_temp(".exe", b"not a real document")

    try:
        _, doc = _run_pipeline(db, path, course.id, "malware.exe")
    finally:
        path.unlink(missing_ok=True)

    assert doc.status == "error"
    assert doc.error_message
    assert "unsupported" in doc.error_message.lower()


@pytest.mark.integration
def test_corrupt_pdf_marks_error_not_stuck(db, tmp_path, monkeypatch):
    """A completely invalid PDF file must not crash the worker or hang forever.
    It should be caught and marked as an error."""
    import uuid
    from app.db.models import CourseDocument
    from app.workers import pipeline
    from contextlib import contextmanager
    
    course, _ = make_course_with_lessons(db)
    doc_id = str(uuid.uuid4())
    
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"This is not a PDF file. It is just some bytes.")

    doc = CourseDocument(
        id=doc_id, course_id=course.id, filename="corrupt.pdf",
        mime_type="application/pdf", size=path.stat().st_size,
        status="processing", processing_stage="queued",
    )
    db.add(doc)
    db.commit()

    @contextmanager
    def isolated_db():
        yield db

    monkeypatch.setattr(pipeline, "get_db_context", isolated_db)
    
    # Run pipeline directly to bypass the WinError 32 bug inside the _run_pipeline helper
    pipeline.run(document_id=doc_id, course_id=course.id, filename="corrupt.pdf", file_path=str(path))
    
    db.refresh(doc)
    
    assert doc.status == "error"
    assert doc.chunk_count in (0, None)
    assert doc.error_message is not None
    
    
    
@pytest.mark.integration
def test_empty_pdf_marks_error_not_stuck(db):
    """A zero-byte file with a .pdf extension — pymupdf4llm raises
    EmptyFileError rather than returning zero pages."""
    course, _ = make_course_with_lessons(db)
    path = _write_temp(".pdf", b"")

    try:
        _, doc = _run_pipeline(db, path, course.id, "empty.pdf")
    finally:
        path.unlink(missing_ok=True)

    assert doc.status == "error"
    assert doc.error_message


@pytest.mark.integration
def test_document_with_no_extractable_text_marks_error(db):
    """A structurally valid PDF whose pages carry no text (a blank page, or a
    page of only images) must be explicitly marked as an error (Issue #263).
    It must reach an ERROR state with a user-facing limitation message,
    and chunk_count == 0."""
    import fitz

    doc_obj = fitz.open()
    doc_obj.new_page()
    path = Path(tempfile.mktemp(suffix=".pdf"))
    doc_obj.save(str(path))
    doc_obj.close()

    course, _ = make_course_with_lessons(db)

    try:
        _, doc = _run_pipeline(db, path, course.id, "blank.pdf")
    finally:
        path.unlink(missing_ok=True)

    assert doc.status == "error", (
        f"A blank document must reach ERROR, not {doc.status}."
    )
    assert doc.chunk_count == 0
    assert doc.page_count == 1
    assert doc.error_message is not None
    assert "No searchable text was extracted" in doc.error_message


# ---------------------------------------------------------------------------
# API-level validation — rejected before a CourseDocument row is even created
# ---------------------------------------------------------------------------

def _auth_header(user) -> dict:
    from app.core.config import create_access_token
    role = getattr(user.role, "value", user.role)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, role)}"}


@pytest.mark.integration
def test_upload_rejects_an_unsupported_mime_type(client, db):
    course, _ = make_course_with_lessons(db)
    user = make_user(db)

    response = client.post(
        f"/api/courses/{course.id}/documents",
        files={"file": ("script.sh", b"#!/bin/sh\necho hi", "application/x-sh")},
        headers=_auth_header(user),
    )

    assert response.status_code == 415
    assert client.get(
        f"/api/courses/{course.id}/documents", headers=_auth_header(user)
    ).json() == [], "A rejected upload must not create a document record"


@pytest.mark.integration
def test_upload_rejects_a_file_over_the_size_limit(client, db):
    course, _ = make_course_with_lessons(db)
    user = make_user(db)
    oversized = b"0" * (50 * 1024 * 1024 + 1)

    with patch("app.api.documents_api.document_service.create_document") as mock_create:
        response = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("huge.pdf", oversized, "application/pdf")},
            headers=_auth_header(user),
        )

    assert response.status_code == 413
    mock_create.assert_not_called()


@pytest.mark.integration
def test_upload_accepts_a_file_exactly_at_the_size_limit(client, db):
    """Boundary check: the limit is inclusive, not off-by-one in the wrong
    direction — a file of exactly 50 MB must not be rejected."""
    course, _ = make_course_with_lessons(db)
    user = make_user(db)
    exactly_at_limit = b"%PDF-1.4\n" + b"0" * (50 * 1024 * 1024 - 9)
    assert len(exactly_at_limit) == 50 * 1024 * 1024

    with patch("app.workers.pipeline.run"):
        response = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("exact.pdf", exactly_at_limit, "application/pdf")},
            headers=_auth_header(user),
        )

    assert response.status_code == 201
