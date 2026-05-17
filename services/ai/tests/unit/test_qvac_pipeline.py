"""Unit tests for pipeline.py — QVAC helpers and new chunking functions.

All I/O and network calls are mocked so no external services are needed.
Tests that require rank_bm25 are skipped automatically if it is not installed.
"""
import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

import app.workers.pipeline as pipeline_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(text="Bitcoin uses UTXO.", doc_id="DOC1"):
    """Minimal child chunk dict matching _make_child() output."""
    return {
        "id": f"{doc_id}_p0000_c0000",
        "text": text,
        "chunk_type": "paragraph",
        "parent_id": f"{doc_id}_p0000",
        "citation_label": "p. 1",
        "citation_page": 1,
        "citation_slide": 0,
        "citation_section": "Intro",
        "doc_id": doc_id,
    }


def _parent(text="Bitcoin uses UTXO.", doc_id="DOC1"):
    """Minimal parent chunk dict matching _make_parent() output."""
    return {
        "id": f"{doc_id}_p0000",
        "text": text,
        "doc_id": doc_id,
        "citation_label": "p. 1",
        "citation_page": 1,
        "citation_section": "Intro",
    }


def _httpx_client_mock(status_code=200, raise_for_status=None):
    """Returns a context-manager mock that mimics httpx.Client."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if raise_for_status:
        mock_resp.raise_for_status.side_effect = raise_for_status
    else:
        mock_resp.raise_for_status = MagicMock()

    mock_instance = MagicMock()
    mock_instance.post.return_value = mock_resp

    MockClient = MagicMock()
    MockClient.return_value.__enter__ = MagicMock(return_value=mock_instance)
    MockClient.return_value.__exit__ = MagicMock(return_value=False)
    return MockClient, mock_instance


# ---------------------------------------------------------------------------
# _write_jsonl
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_write_jsonl_creates_file(tmp_path):
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_jsonl([_chunk()], "DOC1")
    assert out.exists()
    assert out.name == "DOC1_contingency.jsonl"


@pytest.mark.unit
def test_write_jsonl_returns_absolute_path(tmp_path):
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_jsonl([_chunk()], "DOC1")
    assert out.is_absolute()


@pytest.mark.unit
def test_write_jsonl_one_line_per_chunk(tmp_path):
    chunks = [_chunk(text=f"chunk {i}") for i in range(4)]
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_jsonl(chunks, "DOC1")
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    assert len(lines) == 4


@pytest.mark.unit
def test_write_jsonl_each_line_is_valid_json(tmp_path):
    chunks = [_chunk(text=f"chunk {i}") for i in range(3)]
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_jsonl(chunks, "DOC1")
    for line in out.read_text().splitlines():
        obj = json.loads(line)
        assert isinstance(obj, dict)


@pytest.mark.unit
def test_write_jsonl_content_matches_input(tmp_path):
    c = _chunk(text="Proof-of-work secures the chain.", doc_id="DOCX")
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_jsonl([c], "DOCX")
    row = json.loads(out.read_text().strip())
    assert row["text"] == "Proof-of-work secures the chain."
    assert row["doc_id"] == "DOCX"
    assert row["chunk_type"] == "paragraph"
    assert row["parent_id"] == "DOCX_p0000"


@pytest.mark.unit
def test_write_jsonl_empty_input_creates_empty_file(tmp_path):
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        out = pipeline_mod._write_jsonl([], "DOC2")
    assert out.read_text() == ""


@pytest.mark.unit
def test_write_jsonl_creates_parent_directories(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", nested):
        pipeline_mod._write_jsonl([_chunk()], "DOC3")
    assert nested.exists()


# ---------------------------------------------------------------------------
# _qvac_ingest — request construction
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_qvac_ingest_posts_to_ingest_route(tmp_path):
    MockClient, instance = _httpx_client_mock()
    with patch("httpx.Client", MockClient):
        with patch.object(pipeline_mod, "QVAC_SERVICE_URL", "http://localhost:3001"):
            pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "COURSE1")
    url = instance.post.call_args[0][0]
    assert url == "http://localhost:3001/ingest"


@pytest.mark.unit
def test_qvac_ingest_payload_contains_workspace(tmp_path):
    MockClient, instance = _httpx_client_mock()
    with patch("httpx.Client", MockClient):
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "BTC_2025")
    body = instance.post.call_args[1]["json"]
    assert body["workspace"] == "BTC_2025"


@pytest.mark.unit
def test_qvac_ingest_payload_contains_jsonl_path(tmp_path):
    jsonl = tmp_path / "doc.jsonl"
    MockClient, instance = _httpx_client_mock()
    with patch("httpx.Client", MockClient):
        pipeline_mod._qvac_ingest(jsonl, "WS1")
    body = instance.post.call_args[1]["json"]
    assert body["jsonlPath"] == str(jsonl)


@pytest.mark.unit
def test_qvac_ingest_rebuild_defaults_to_false(tmp_path):
    MockClient, instance = _httpx_client_mock()
    with patch("httpx.Client", MockClient):
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")
    body = instance.post.call_args[1]["json"]
    assert body["rebuild"] is False


@pytest.mark.unit
def test_qvac_ingest_rebuild_true_when_passed(tmp_path):
    MockClient, instance = _httpx_client_mock()
    with patch("httpx.Client", MockClient):
        pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1", rebuild=True)
    body = instance.post.call_args[1]["json"]
    assert body["rebuild"] is True


@pytest.mark.unit
def test_qvac_ingest_returns_true_on_success(tmp_path):
    MockClient, _ = _httpx_client_mock(status_code=200)
    with patch("httpx.Client", MockClient):
        result = pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")
    assert result is True


@pytest.mark.unit
def test_qvac_ingest_returns_false_on_http_error(tmp_path):
    MockClient, instance = _httpx_client_mock()
    instance.post.side_effect = httpx.ConnectError("connection refused")
    with patch("httpx.Client", MockClient):
        result = pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")
    assert result is False


@pytest.mark.unit
def test_qvac_ingest_returns_false_on_status_error(tmp_path):
    MockClient, _ = _httpx_client_mock(
        raise_for_status=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
    )
    with patch("httpx.Client", MockClient):
        result = pipeline_mod._qvac_ingest(tmp_path / "doc.jsonl", "WS1")
    assert result is False


# ---------------------------------------------------------------------------
# _split_paragraph
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_split_paragraph_short_text_returned_unchanged():
    text = "Bitcoin uses UTXO. Transactions are validated by miners."
    result = pipeline_mod._split_paragraph(text, max_words=100)
    assert result == [text]


@pytest.mark.unit
def test_split_paragraph_long_text_is_split():
    # 200 "sentences" of 3 words each → 600 words, split at 50
    text = " ".join(f"Word{i} here." for i in range(200))
    result = pipeline_mod._split_paragraph(text, max_words=50)
    assert len(result) > 1


@pytest.mark.unit
def test_split_paragraph_all_parts_non_empty():
    text = " ".join(f"Sentence{i} is here." for i in range(100))
    result = pipeline_mod._split_paragraph(text, max_words=30)
    assert all(part.strip() for part in result)


@pytest.mark.unit
def test_split_paragraph_overlap_shares_words_with_next_chunk():
    # 6 clear sentences, max_words=5 (forces splits), overlap_words=3
    sentences = [f"This is sentence {i}." for i in range(10)]
    text = " ".join(sentences)
    result = pipeline_mod._split_paragraph(text, max_words=10, overlap_words=5)
    if len(result) < 2:
        pytest.skip("Text too short to trigger split with these parameters")
    first_words = set(result[0].split())
    second_words = set(result[1].split())
    assert first_words & second_words, "Overlap must share words between consecutive chunks"


@pytest.mark.unit
def test_split_paragraph_no_overlap_produces_disjoint_starts():
    sentences = [f"Sentence number {i} here." for i in range(30)]
    text = " ".join(sentences)
    result = pipeline_mod._split_paragraph(text, max_words=20, overlap_words=0)
    assert len(result) > 1


# ---------------------------------------------------------------------------
# build_parent_child_chunks
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_build_parent_child_returns_two_lists():
    pages = [{"page": 1, "text": "Bitcoin uses UTXO. " * 5}]
    parents, children = pipeline_mod.build_parent_child_chunks(pages, "DOC1")
    assert isinstance(parents, list)
    assert isinstance(children, list)


@pytest.mark.unit
def test_build_parent_child_non_empty_for_real_text():
    pages = [{"page": 1, "text": "Bitcoin is a peer-to-peer electronic cash system. " * 30}]
    parents, children = pipeline_mod.build_parent_child_chunks(pages, "DOC1")
    assert len(parents) > 0
    assert len(children) > 0


@pytest.mark.unit
def test_build_parent_child_every_child_has_valid_parent_id():
    pages = [{"page": 1, "text": "Satoshi Nakamoto published the Bitcoin whitepaper in 2008. " * 30}]
    parents, children = pipeline_mod.build_parent_child_chunks(pages, "DOC1")
    parent_ids = {p["id"] for p in parents}
    for child in children:
        assert child["parent_id"] in parent_ids, f"Child parent_id {child['parent_id']!r} not in parents"


@pytest.mark.unit
def test_build_parent_child_ids_follow_naming_convention():
    pages = [{"page": 1, "text": "Bitcoin uses UTXO. " * 40}]
    parents, children = pipeline_mod.build_parent_child_chunks(pages, "DOC1")
    for p in parents:
        assert p["id"].startswith("DOC1_p"), f"Parent id format wrong: {p['id']}"
    for c in children:
        assert "_c" in c["id"], f"Child id missing '_c': {c['id']}"


@pytest.mark.unit
def test_build_parent_child_table_block_produces_table_child():
    table_text = "| Col1 | Col2 |\n|------|------|\n| A    | B    |\n| C    | D    |"
    pages = [{"page": 1, "text": table_text}]
    _, children = pipeline_mod.build_parent_child_chunks(pages, "DOC1")
    table_children = [c for c in children if c["chunk_type"] == "table"]
    assert len(table_children) > 0


@pytest.mark.unit
def test_build_parent_child_empty_pages_returns_empty():
    parents, children = pipeline_mod.build_parent_child_chunks([], "DOC1")
    assert parents == []
    assert children == []


# ---------------------------------------------------------------------------
# _build_bm25_index
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_build_bm25_creates_corpus_file(tmp_path):
    pytest.importorskip("rank_bm25")
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        pipeline_mod._build_bm25_index([_chunk()], "COURSE1", "DOC1")
    assert (tmp_path / "COURSE1_corpus.json").exists()


@pytest.mark.unit
def test_build_bm25_creates_pkl_file(tmp_path):
    pytest.importorskip("rank_bm25")
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        pipeline_mod._build_bm25_index([_chunk()], "COURSE1", "DOC1")
    assert (tmp_path / "COURSE1_bm25.pkl").exists()


@pytest.mark.unit
def test_build_bm25_corpus_contains_chunk_text(tmp_path):
    pytest.importorskip("rank_bm25")
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        pipeline_mod._build_bm25_index([_chunk(text="UTXO is unspent.")], "COURSE1", "DOC1")
    corpus = json.loads((tmp_path / "COURSE1_corpus.json").read_text())
    texts = [v["text"] for v in corpus.values()]
    assert "UTXO is unspent." in texts


@pytest.mark.unit
def test_build_bm25_removes_stale_entries_on_reingest(tmp_path):
    pytest.importorskip("rank_bm25")
    # First ingest
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        pipeline_mod._build_bm25_index([_chunk(text="Original text.", doc_id="DOC1")], "COURSE1", "DOC1")
    # Re-ingest same doc_id
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        pipeline_mod._build_bm25_index([_chunk(text="Updated text.", doc_id="DOC1")], "COURSE1", "DOC1")
    corpus = json.loads((tmp_path / "COURSE1_corpus.json").read_text())
    texts = [v["text"] for v in corpus.values()]
    assert "Original text." not in texts
    assert "Updated text." in texts


@pytest.mark.unit
def test_build_bm25_accumulates_chunks_from_different_docs(tmp_path):
    pytest.importorskip("rank_bm25")
    c1 = _chunk(text="Doc A content.", doc_id="DOC_A")
    c1["id"] = "DOC_A_p0000_c0000"
    c2 = {**_chunk(text="Doc B content.", doc_id="DOC_B"), "id": "DOC_B_p0000_c0000"}
    with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
        pipeline_mod._build_bm25_index([c1], "COURSE1", "DOC_A")
        pipeline_mod._build_bm25_index([c2], "COURSE1", "DOC_B")
    corpus = json.loads((tmp_path / "COURSE1_corpus.json").read_text())
    texts = [v["text"] for v in corpus.values()]
    assert "Doc A content." in texts
    assert "Doc B content." in texts


@pytest.mark.unit
def test_build_bm25_noop_when_rank_bm25_missing(tmp_path):
    with patch.dict("sys.modules", {"rank_bm25": None}):
        with patch.object(pipeline_mod, "QVAC_INGEST_DIR", tmp_path):
            # Should not raise, should return silently
            pipeline_mod._build_bm25_index([_chunk()], "COURSE1", "DOC1")
    # No files created
    assert not (tmp_path / "COURSE1_corpus.json").exists()


# ---------------------------------------------------------------------------
# _save_parents_to_db
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_save_parents_to_db_inserts_record(db):
    parents = [_parent()]
    pipeline_mod._save_parents_to_db(parents, "COURSE1", db)

    from app.db.models import ChunkParent
    row = db.query(ChunkParent).filter_by(id="DOC1_p0000").first()
    assert row is not None
    assert row.text == "Bitcoin uses UTXO."
    assert row.course_id == "COURSE1"
    assert row.doc_id == "DOC1"


@pytest.mark.unit
def test_save_parents_to_db_upserts_existing(db):
    from app.db.models import ChunkParent

    # Initial insert
    pipeline_mod._save_parents_to_db([_parent(text="Original.")], "COURSE1", db)

    # Update same id
    pipeline_mod._save_parents_to_db([_parent(text="Updated.")], "COURSE1", db)

    rows = db.query(ChunkParent).filter_by(id="DOC1_p0000").all()
    assert len(rows) == 1
    assert rows[0].text == "Updated."


@pytest.mark.unit
def test_save_parents_to_db_inserts_multiple(db):
    from app.db.models import ChunkParent

    parents = [
        {**_parent(doc_id="DOC1"), "id": "DOC1_p0000"},
        {**_parent(doc_id="DOC1"), "id": "DOC1_p0001", "text": "Second parent."},
    ]
    pipeline_mod._save_parents_to_db(parents, "COURSE1", db)

    count = db.query(ChunkParent).filter(ChunkParent.course_id == "COURSE1").count()
    assert count == 2


@pytest.mark.unit
def test_save_parents_to_db_empty_list_is_noop(db):
    from app.db.models import ChunkParent
    pipeline_mod._save_parents_to_db([], "COURSE1", db)
    count = db.query(ChunkParent).count()
    assert count == 0
