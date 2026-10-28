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
def test_corrupt_pdf_marks_error_not_stuck(db):
    """Garbage bytes with a .pdf extension — pymupdf4llm raises FileDataError;
    the pipeline's outer exception handler must turn that into a terminal
    error state, not propagate it (which would leave the document mid-flight
    forever if this ran as a background task with no caller to catch it)."""
    course, _ = make_course_with_lessons(db)
    path = _write_temp(".pdf", b"this is not a pdf, just garbage bytes 12345")

    try:
        _, doc = _run_pipeline(db, path, course.id, "corrupt.pdf")
    finally:
        path.unlink(missing_ok=True)

    assert doc.status == "error"
    assert doc.error_message


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
    page of only images, #263) has nothing to index: it must end in ERROR with
    a message explaining that scanned PDFs are not supported, not in a READY
    state that looks searchable."""
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

    assert doc.status == "error"
    assert doc.processing_stage == "error"
    assert "No searchable text" in doc.error_message
    assert doc.chunk_count == 0
    assert doc.page_count == 1


# ---------------------------------------------------------------------------
# QVAC dense index failures — the document stays usable through BM25
# ---------------------------------------------------------------------------

_TEXT = "# Bitcoin\n\n" + "Bitcoin is a peer-to-peer electronic cash system. " * 40


@pytest.mark.integration
@pytest.mark.parametrize("qvac_status", ["qvac_pending", "qvac_failed"])
def test_qvac_failure_keeps_document_ready_and_reports_indexing_status(db, tmp_path, qvac_status):
    """Unreachable (pending) and rejected (failed) QVAC ingests both leave the
    chunks and BM25 usable, so the document is READY and indexing_status says
    which dense-index problem the UI must show."""
    course, _ = make_course_with_lessons(db)
    path = tmp_path / "notes.md"
    path.write_text(_TEXT, encoding="utf-8")

    _, doc = _run_pipeline(db, path, course.id, path.name, qvac_status=qvac_status)

    assert doc.status == "ready"
    assert doc.indexing_status == qvac_status
    assert doc.chunk_count > 0
    assert doc.error_message is None


@pytest.mark.integration
@pytest.mark.parametrize(("qvac_status", "expected"), [
    ("indexed", "indexed"),
    ("qvac_failed", "qvac_failed"),
])
def test_reindex_updates_indexing_status_and_keeps_document_ready(
    db, tmp_path, monkeypatch, qvac_status, expected
):
    from contextlib import contextmanager

    import app.workers.pipeline as pipeline_mod
    from app.db.models import CourseDocument

    course, _ = make_course_with_lessons(db)
    doc = CourseDocument(
        course_id=course.id, filename="notes.md", mime_type="text/markdown", size=10,
        status="ready", processing_stage="done", indexing_status="qvac_failed",
    )
    db.add(doc)
    db.commit()
    (tmp_path / f"{doc.id}_contingency.jsonl").write_text("{}\n")

    @contextmanager
    def _fake_db_ctx():
        yield db

    monkeypatch.setattr(pipeline_mod, "QVAC_INGEST_DIR", tmp_path)
    monkeypatch.setattr(pipeline_mod, "get_db_context", _fake_db_ctx)
    with patch("app.workers.pipeline._qvac_ingest", return_value=qvac_status) as mock_qvac:
        pipeline_mod.reindex_qvac(doc.id, course.id)

    db.refresh(doc)
    assert mock_qvac.call_args.kwargs["rebuild"] is True
    assert doc.status == "ready"
    assert doc.indexing_status == expected


@pytest.mark.integration
def test_document_list_exposes_indexing_status(client, db):
    from app.db.models import CourseDocument

    course, _ = make_course_with_lessons(db)
    user = make_user(db)
    db.add(CourseDocument(
        course_id=course.id, filename="notes.md", mime_type="text/markdown", size=10,
        status="ready", processing_stage="done", indexing_status="qvac_failed",
    ))
    db.commit()

    rows = client.get(f"/api/courses/{course.id}/documents", headers=_auth_header(user)).json()

    assert rows[0]["indexing_status"] == "qvac_failed"


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
