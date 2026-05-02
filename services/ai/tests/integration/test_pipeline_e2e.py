"""End-to-end pipeline integration tests using real fixture files.

These tests exercise the full chain:
  PDF/PPTX → StructuralParser → Chunker → ChromaDB (temp dir) → QVAC ingest

The pipeline.run() function is tested with a temp ChromaDB, a temp QVAC ingest
directory, and a real DB session (in-memory SQLite via conftest).
fastembed and chromadb must be installed.

_qvac_ingest is patched in _run_pipeline() to avoid network calls — the QVAC
service doesn't need to be running for these tests. QVAC-specific assertions
(JSONL content, call args) are in dedicated tests that set up their own context.

Marked @pytest.mark.slow — excluded from the default fast test run.
"""
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db.models import DocumentProcessingStage, DocumentStatus
from tests.conftest import make_course_with_lessons, make_user

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOCS = _REPO_ROOT / "docs" / "src"
PDF_PATH = _DOCS / "bitcoin_technical_document.pdf"
PPTX_PATH = _DOCS / "bitcoin_creative_commons_en.pptx"


def _skip_if_missing(path: Path):
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")


def _try_import(module_name: str):
    try:
        __import__(module_name)
    except ImportError:
        pytest.skip(f"{module_name} not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_pipeline(db, file_path: Path, course_id: str, filename: str) -> tuple:
    """Run pipeline.run() with isolated ChromaDB and QVAC dirs.

    _qvac_ingest is patched so no HTTP call is made to the QVAC service.
    The JSONL file is still written to a temp directory (tests can inspect it
    separately if needed). Returns (doc_id, doc_record).
    """
    _try_import("fastembed")
    _try_import("chromadb")

    import app.workers.pipeline as pipeline_mod

    doc_id = str(uuid.uuid4())

    from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus
    doc = CourseDocument(
        id=doc_id,
        course_id=course_id,
        filename=filename,
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.UPLOADING,
        size=file_path.stat().st_size,
        mime_type="application/pdf",
    )
    db.add(doc)
    db.commit()

    with tempfile.TemporaryDirectory() as tmp_chroma:
        with tempfile.TemporaryDirectory() as tmp_qvac:
            pipeline_mod.CHROMA_DB_PATH = tmp_chroma
            pipeline_mod.QVAC_INGEST_DIR = Path(tmp_qvac)

            with tempfile.NamedTemporaryFile(
                suffix=Path(filename).suffix, delete=False
            ) as tmp_file:
                tmp_file.write(file_path.read_bytes())
                tmp_path = tmp_file.name

            try:
                from contextlib import contextmanager

                @contextmanager
                def _fake_db_ctx():
                    yield db

                # Patch _qvac_ingest to avoid requiring the QVAC service to be running
                with patch("app.workers.pipeline._qvac_ingest"):
                    with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
                        pipeline_mod.run(
                            document_id=doc_id,
                            course_id=course_id,
                            filename=filename,
                            file_path=tmp_path,
                        )
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    db.refresh(doc)
    return doc_id, doc


# ---------------------------------------------------------------------------
# PDF end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pdf_status_becomes_ready(client, db):
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    doc_id, doc = _run_pipeline(db, PDF_PATH, course.id, "bitcoin_technical_document.pdf")

    assert doc.status == DocumentStatus.READY
    assert doc.processing_stage == DocumentProcessingStage.DONE


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pdf_chunk_count_positive(client, db):
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    _, doc = _run_pipeline(db, PDF_PATH, course.id, "bitcoin_technical_document.pdf")

    assert doc.chunk_count is not None
    assert doc.chunk_count > 0


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pdf_page_count_is_4(client, db):
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    _, doc = _run_pipeline(db, PDF_PATH, course.id, "bitcoin_technical_document.pdf")

    assert doc.page_count == 4


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pdf_sections_json_non_empty(client, db):
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    _, doc = _run_pipeline(db, PDF_PATH, course.id, "bitcoin_technical_document.pdf")

    assert doc.sections_json is not None
    sections = json.loads(doc.sections_json)
    assert isinstance(sections, list)
    assert len(sections) > 0


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pdf_sample_chunks_json_present(client, db):
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    _, doc = _run_pipeline(db, PDF_PATH, course.id, "bitcoin_technical_document.pdf")

    assert doc.sample_chunks_json is not None
    samples = json.loads(doc.sample_chunks_json)
    assert isinstance(samples, list)
    assert len(samples) > 0
    for s in samples:
        assert "text" in s
        assert "label" in s


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pdf_text_preview_non_empty(client, db):
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    _, doc = _run_pipeline(db, PDF_PATH, course.id, "bitcoin_technical_document.pdf")

    assert doc.extracted_text_preview
    assert len(doc.extracted_text_preview) > 0


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pdf_temp_file_cleaned_up(client, db):
    """The uploaded temp file should be deleted by the pipeline after indexing."""
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    import app.workers.pipeline as pipeline_mod

    course, _ = make_course_with_lessons(db)
    doc_id = str(uuid.uuid4())

    from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus
    doc = CourseDocument(
        id=doc_id,
        course_id=course.id,
        filename="bitcoin_technical_document.pdf",
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.UPLOADING,
        size=PDF_PATH.stat().st_size,
        mime_type="application/pdf",
    )
    db.add(doc)
    db.commit()

    with tempfile.TemporaryDirectory() as tmp_chroma:
        pipeline_mod.CHROMA_DB_PATH = tmp_chroma
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(PDF_PATH.read_bytes())
            tmp_path = f.name

        try:
            from contextlib import contextmanager

            @contextmanager
            def _fake_db_ctx():
                yield db

            with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
                pipeline_mod.run(
                    document_id=doc_id,
                    course_id=course.id,
                    filename="bitcoin_technical_document.pdf",
                    file_path=tmp_path,
                )

            assert not os.path.exists(tmp_path), "Temp file was not cleaned up after pipeline"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


# ---------------------------------------------------------------------------
# PPTX end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pptx_status_becomes_ready(client, db):
    _skip_if_missing(PPTX_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    _, doc = _run_pipeline(db, PPTX_PATH, course.id, "bitcoin_creative_commons_en.pptx")

    assert doc.status == DocumentStatus.READY


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_pptx_chunk_count_positive(client, db):
    _skip_if_missing(PPTX_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    course, _ = make_course_with_lessons(db)
    _, doc = _run_pipeline(db, PPTX_PATH, course.id, "bitcoin_creative_commons_en.pptx")

    assert doc.chunk_count is not None
    assert doc.chunk_count > 0


# ---------------------------------------------------------------------------
# Error handling — bad file path
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_pipeline_nonexistent_file_marks_error(client, db):
    """Pipeline should catch the exception and mark status=ERROR."""
    import app.workers.pipeline as pipeline_mod

    course, _ = make_course_with_lessons(db)
    doc_id = str(uuid.uuid4())

    from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus
    doc = CourseDocument(
        id=doc_id,
        course_id=course.id,
        filename="ghost.pdf",
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.UPLOADING,
        size=0,
        mime_type="application/pdf",
    )
    db.add(doc)
    db.commit()

    from contextlib import contextmanager

    @contextmanager
    def _fake_db_ctx():
        yield db

    with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
        pipeline_mod.run(
            document_id=doc_id,
            course_id=course.id,
            filename="ghost.pdf",
            file_path="/tmp/does_not_exist_abc123.pdf",
        )

    db.refresh(doc)
    assert doc.status == DocumentStatus.ERROR


@pytest.mark.integration
def test_pipeline_unknown_document_id_does_not_raise(client, db):
    """Pipeline should exit gracefully when document_id is not in DB."""
    import app.workers.pipeline as pipeline_mod

    from contextlib import contextmanager

    @contextmanager
    def _fake_db_ctx():
        yield db

    # Should not raise — just logs error and returns
    with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
        pipeline_mod.run(
            document_id="nonexistent-doc-id",
            course_id="course-x",
            filename="x.pdf",
            file_path="/tmp/x.pdf",
        )


# ---------------------------------------------------------------------------
# QVAC integration — verifies the JSONL write + _qvac_ingest call
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_writes_qvac_jsonl_for_pdf(client, db):
    """After a successful run, a JSONL file must exist in QVAC_INGEST_DIR."""
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    import app.workers.pipeline as pipeline_mod
    from contextlib import contextmanager
    from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus

    course, _ = make_course_with_lessons(db)
    doc_id = str(uuid.uuid4())
    doc = CourseDocument(
        id=doc_id, course_id=course.id, filename="bitcoin_technical_document.pdf",
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.UPLOADING,
        size=PDF_PATH.stat().st_size, mime_type="application/pdf",
    )
    db.add(doc)
    db.commit()

    with tempfile.TemporaryDirectory() as tmp_chroma:
        with tempfile.TemporaryDirectory() as tmp_qvac:
            pipeline_mod.CHROMA_DB_PATH = tmp_chroma
            pipeline_mod.QVAC_INGEST_DIR = Path(tmp_qvac)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(PDF_PATH.read_bytes())
                tmp_path = f.name

            try:
                @contextmanager
                def _fake_db_ctx():
                    yield db

                with patch("app.workers.pipeline._qvac_ingest"):
                    with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
                        pipeline_mod.run(
                            document_id=doc_id, course_id=course.id,
                            filename="bitcoin_technical_document.pdf", file_path=tmp_path,
                        )
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            expected_jsonl = Path(tmp_qvac) / f"{doc_id}_contingency.jsonl"
            assert expected_jsonl.exists(), "JSONL file not written to QVAC_INGEST_DIR"


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_qvac_jsonl_contains_only_paragraph_chunks(client, db):
    """JSONL written by the pipeline must contain only paragraph-type chunks."""
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    import app.workers.pipeline as pipeline_mod
    from contextlib import contextmanager
    from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus

    course, _ = make_course_with_lessons(db)
    doc_id = str(uuid.uuid4())
    doc = CourseDocument(
        id=doc_id, course_id=course.id, filename="bitcoin_technical_document.pdf",
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.UPLOADING,
        size=PDF_PATH.stat().st_size, mime_type="application/pdf",
    )
    db.add(doc)
    db.commit()

    with tempfile.TemporaryDirectory() as tmp_chroma:
        with tempfile.TemporaryDirectory() as tmp_qvac:
            pipeline_mod.CHROMA_DB_PATH = tmp_chroma
            pipeline_mod.QVAC_INGEST_DIR = Path(tmp_qvac)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(PDF_PATH.read_bytes())
                tmp_path = f.name

            try:
                @contextmanager
                def _fake_db_ctx():
                    yield db

                with patch("app.workers.pipeline._qvac_ingest"):
                    with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
                        pipeline_mod.run(
                            document_id=doc_id, course_id=course.id,
                            filename="bitcoin_technical_document.pdf", file_path=tmp_path,
                        )
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            jsonl_path = Path(tmp_qvac) / f"{doc_id}_contingency.jsonl"
            rows = [json.loads(l) for l in jsonl_path.read_text().splitlines()]
            assert len(rows) > 0
            for row in rows:
                assert row["chunk_type"] == "paragraph", (
                    f"non-paragraph chunk found in QVAC JSONL: {row['chunk_type']}"
                )


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_qvac_ingest_called_with_course_id_as_workspace(client, db):
    """_qvac_ingest must be called with workspace equal to course_id."""
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    import app.workers.pipeline as pipeline_mod
    from contextlib import contextmanager
    from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus

    course, _ = make_course_with_lessons(db)
    doc_id = str(uuid.uuid4())
    doc = CourseDocument(
        id=doc_id, course_id=course.id, filename="bitcoin_technical_document.pdf",
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.UPLOADING,
        size=PDF_PATH.stat().st_size, mime_type="application/pdf",
    )
    db.add(doc)
    db.commit()

    with tempfile.TemporaryDirectory() as tmp_chroma:
        with tempfile.TemporaryDirectory() as tmp_qvac:
            pipeline_mod.CHROMA_DB_PATH = tmp_chroma
            pipeline_mod.QVAC_INGEST_DIR = Path(tmp_qvac)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(PDF_PATH.read_bytes())
                tmp_path = f.name

            try:
                @contextmanager
                def _fake_db_ctx():
                    yield db

                with patch("app.workers.pipeline._qvac_ingest") as mock_qvac:
                    with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
                        pipeline_mod.run(
                            document_id=doc_id, course_id=course.id,
                            filename="bitcoin_technical_document.pdf", file_path=tmp_path,
                        )
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    mock_qvac.assert_called_once()
    _, call_kwargs = mock_qvac.call_args
    assert call_kwargs["workspace"] == course.id
    assert call_kwargs["rebuild"] is True


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_qvac_jsonl_has_required_fields(client, db):
    """Each row in the QVAC JSONL must carry the fields that ingest.js reads."""
    _skip_if_missing(PDF_PATH)
    _try_import("fastembed")
    _try_import("chromadb")

    import app.workers.pipeline as pipeline_mod
    from contextlib import contextmanager
    from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus

    course, _ = make_course_with_lessons(db)
    doc_id = str(uuid.uuid4())
    doc = CourseDocument(
        id=doc_id, course_id=course.id, filename="bitcoin_technical_document.pdf",
        status=DocumentStatus.PROCESSING,
        processing_stage=DocumentProcessingStage.UPLOADING,
        size=PDF_PATH.stat().st_size, mime_type="application/pdf",
    )
    db.add(doc)
    db.commit()

    required_fields = {"chunk_id", "doc_id", "course_id", "chunk_type", "text"}

    with tempfile.TemporaryDirectory() as tmp_chroma:
        with tempfile.TemporaryDirectory() as tmp_qvac:
            pipeline_mod.CHROMA_DB_PATH = tmp_chroma
            pipeline_mod.QVAC_INGEST_DIR = Path(tmp_qvac)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(PDF_PATH.read_bytes())
                tmp_path = f.name

            try:
                @contextmanager
                def _fake_db_ctx():
                    yield db

                with patch("app.workers.pipeline._qvac_ingest"):
                    with patch("app.workers.pipeline.get_db_context", _fake_db_ctx):
                        pipeline_mod.run(
                            document_id=doc_id, course_id=course.id,
                            filename="bitcoin_technical_document.pdf", file_path=tmp_path,
                        )
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            jsonl_path = Path(tmp_qvac) / f"{doc_id}_contingency.jsonl"
            rows = [json.loads(l) for l in jsonl_path.read_text().splitlines()]
            assert len(rows) > 0
            for row in rows:
                missing = required_fields - row.keys()
                assert not missing, f"JSONL row missing fields: {missing}"
