"""Unit tests for the QVAC integration in pipeline.py.

Covers _write_qvac_jsonl and _qvac_ingest without loading fastembed,
chromadb, or any ML model. All I/O and network calls are mocked.
"""
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import app.workers.pipeline as pipeline_mod


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _chunk(text="Bitcoin uses UTXO.", doc_id="DOC1", course_id="COURSE1"):
    """Minimal DocumentChunk-like mock with a working model_dump()."""
    c = MagicMock()
    c.model_dump.return_value = {
        "chunk_id": "abc-123",
        "doc_id": doc_id,
        "course_id": course_id,
        "chunk_type": "paragraph",
        "text": text,
        "citation_label": "p. 1",
        "citation_page": 1,
        "citation_slide": None,
        "citation_section": "Intro",
        "parent_chunk_id": None,
        "tags": [],
        "prerequisites": [],
    }
    return c


def _mock_urlopen_response(status=200):
    """Context-manager mock that mimics the urllib response object."""
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# _write_qvac_jsonl
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_write_qvac_jsonl_creates_file(tmp_path):
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_qvac_jsonl([_chunk()], "DOC1")
    assert out.exists()
    assert out.name == "DOC1_contingency.jsonl"


@pytest.mark.unit
def test_write_qvac_jsonl_returns_absolute_path(tmp_path):
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_qvac_jsonl([_chunk()], "DOC1")
    assert out.is_absolute()


@pytest.mark.unit
def test_write_qvac_jsonl_one_line_per_chunk(tmp_path):
    chunks = [_chunk(text=f"chunk {i}") for i in range(4)]
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_qvac_jsonl(chunks, "DOC1")
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    assert len(lines) == 4


@pytest.mark.unit
def test_write_qvac_jsonl_each_line_is_valid_json(tmp_path):
    chunks = [_chunk(text=f"chunk {i}") for i in range(3)]
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_qvac_jsonl(chunks, "DOC1")
    for line in out.read_text().splitlines():
        obj = json.loads(line)
        assert isinstance(obj, dict)


@pytest.mark.unit
def test_write_qvac_jsonl_content_matches_model_dump(tmp_path):
    c = _chunk(text="Proof-of-work secures the chain.", doc_id="DOCX", course_id="C42")
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_qvac_jsonl([c], "DOCX")
    row = json.loads(out.read_text().strip())
    assert row["text"] == "Proof-of-work secures the chain."
    assert row["doc_id"] == "DOCX"
    assert row["course_id"] == "C42"


@pytest.mark.unit
def test_write_qvac_jsonl_empty_input_creates_empty_file(tmp_path):
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_qvac_jsonl([], "DOC2")
    assert out.read_text() == ""


@pytest.mark.unit
def test_write_qvac_jsonl_creates_parent_directories(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", nested):
        pipeline_mod._write_qvac_jsonl([_chunk()], "DOC3")
    assert nested.exists()


# ---------------------------------------------------------------------------
# _qvac_ingest — request construction
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_qvac_ingest_posts_to_ingest_route(tmp_path):
    jsonl = tmp_path / "doc.jsonl"
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
        with patch.object(pipeline_mod, "QVAC_SERVICE_URL", "http://localhost:3001"):
            pipeline_mod._qvac_ingest(jsonl, "COURSE1")
    req = mock_open.call_args[0][0]
    assert req.full_url == "http://localhost:3001/ingest"
    assert req.method == "POST"


@pytest.mark.unit
def test_qvac_ingest_payload_contains_workspace(tmp_path):
    jsonl = tmp_path / "doc.jsonl"
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
        pipeline_mod._qvac_ingest(jsonl, "BTC_2025")
    body = json.loads(mock_open.call_args[0][0].data)
    assert body["workspace"] == "BTC_2025"


@pytest.mark.unit
def test_qvac_ingest_payload_contains_absolute_jsonl_path(tmp_path):
    jsonl = tmp_path / "doc.jsonl"
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
        pipeline_mod._qvac_ingest(jsonl, "WS1")
    body = json.loads(mock_open.call_args[0][0].data)
    assert body["jsonlPath"] == str(jsonl)


@pytest.mark.unit
def test_qvac_ingest_rebuild_defaults_to_false(tmp_path):
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")
    body = json.loads(mock_open.call_args[0][0].data)
    assert body["rebuild"] is False


@pytest.mark.unit
def test_qvac_ingest_rebuild_true_when_passed(tmp_path):
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1", rebuild=True)
    body = json.loads(mock_open.call_args[0][0].data)
    assert body["rebuild"] is True


@pytest.mark.unit
def test_qvac_ingest_content_type_is_json(tmp_path):
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")
    req = mock_open.call_args[0][0]
    assert req.get_header("Content-type") == "application/json"


# ---------------------------------------------------------------------------
# _qvac_ingest — resilience (service not running must not break the pipeline)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_qvac_ingest_does_not_raise_on_connection_refused(tmp_path):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")  # must not raise


@pytest.mark.unit
def test_qvac_ingest_does_not_raise_on_timeout(tmp_path):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")


@pytest.mark.unit
def test_qvac_ingest_does_not_raise_on_generic_exception(tmp_path):
    with patch("urllib.request.urlopen", side_effect=Exception("unexpected error")):
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")
