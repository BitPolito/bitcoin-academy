"""Unit tests for app.services.hybrid_search — BM25, RRF fusion, and index loading.

Tests that require rank_bm25 are skipped automatically when the library is absent.
"""
import json
import pickle
from pathlib import Path
from unittest.mock import patch

import pytest

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk
from app.services.hybrid_search import bm25_search, load_bm25_index, rrf_fuse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence_chunk(chunk_id: str, score: float = 0.9) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=f"Text for {chunk_id}.",
        score=score,
        anchor=CitationAnchor(
            doc_id="DOC1",
            doc_name="Bitcoin Whitepaper",
            section="Intro",
            page=1,
            slide=None,
            chunk_id=chunk_id,
            chunk_type="paragraph",
        ),
    )


def _write_bm25_index(tmp_path: Path, ids: list, tokenized: list) -> None:
    """Build and persist a BM25 index + corpus to tmp_path."""
    pytest.importorskip("rank_bm25")
    from rank_bm25 import BM25Okapi

    bm25 = BM25Okapi(tokenized)
    corpus = {
        cid: {"text": " ".join(toks), "doc_id": "DOC1", "label": f"p. {i+1}",
              "page": i + 1, "section": "Intro"}
        for i, (cid, toks) in enumerate(zip(ids, tokenized))
    }
    with (tmp_path / "COURSE1_bm25.pkl").open("wb") as f:
        pickle.dump({"bm25": bm25, "ids": ids}, f)
    with (tmp_path / "COURSE1_corpus.json").open("w") as f:
        json.dump(corpus, f)


# ---------------------------------------------------------------------------
# load_bm25_index
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_bm25_index_returns_none_when_files_missing(tmp_path):
    with patch("app.services.hybrid_search._QVAC_INGEST_DIR", tmp_path):
        result = load_bm25_index("NO_SUCH_COURSE")
    assert result is None


@pytest.mark.unit
def test_load_bm25_index_returns_tuple_when_present(tmp_path):
    pytest.importorskip("rank_bm25")
    ids = ["c1", "c2"]
    tokenized = [["bitcoin", "utxo"], ["proof", "work"]]
    _write_bm25_index(tmp_path, ids, tokenized)

    with patch("app.services.hybrid_search._QVAC_INGEST_DIR", tmp_path):
        result = load_bm25_index("COURSE1")

    assert result is not None
    bm25_obj, returned_ids, corpus = result
    assert returned_ids == ids
    assert isinstance(corpus, dict)
    assert "c1" in corpus


@pytest.mark.unit
def test_load_bm25_index_returns_none_on_corrupt_pickle(tmp_path):
    (tmp_path / "COURSE1_bm25.pkl").write_bytes(b"not a valid pickle")
    (tmp_path / "COURSE1_corpus.json").write_text("{}")
    with patch("app.services.hybrid_search._QVAC_INGEST_DIR", tmp_path):
        result = load_bm25_index("COURSE1")
    assert result is None


# ---------------------------------------------------------------------------
# bm25_search
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_bm25_search_returns_empty_when_index_missing(tmp_path):
    with patch("app.services.hybrid_search._QVAC_INGEST_DIR", tmp_path):
        result = bm25_search("bitcoin", "NO_COURSE", top_k=5)
    assert result == []


@pytest.mark.unit
def test_bm25_search_returns_ranked_tuples(tmp_path):
    pytest.importorskip("rank_bm25")
    ids = ["chunk_bitcoin", "chunk_mining"]
    tokenized = [["bitcoin", "utxo", "transaction"], ["proof", "work", "mining"]]
    _write_bm25_index(tmp_path, ids, tokenized)

    with patch("app.services.hybrid_search._QVAC_INGEST_DIR", tmp_path):
        results = bm25_search("bitcoin utxo", "COURSE1", top_k=5)

    assert len(results) > 0
    assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
    # Most relevant chunk for "bitcoin utxo" should rank first
    assert results[0][0] == "chunk_bitcoin"


@pytest.mark.unit
def test_bm25_search_excludes_zero_scores(tmp_path):
    pytest.importorskip("rank_bm25")
    ids = ["relevant", "irrelevant"]
    tokenized = [["bitcoin", "utxo"], ["astronomy", "stars"]]
    _write_bm25_index(tmp_path, ids, tokenized)

    with patch("app.services.hybrid_search._QVAC_INGEST_DIR", tmp_path):
        results = bm25_search("bitcoin", "COURSE1", top_k=10)

    chunk_ids = [r[0] for r in results]
    assert "irrelevant" not in chunk_ids
    assert "relevant" in chunk_ids


@pytest.mark.unit
def test_bm25_search_respects_top_k(tmp_path):
    pytest.importorskip("rank_bm25")
    ids = [f"c{i}" for i in range(10)]
    tokenized = [["bitcoin", f"token{i}"] for i in range(10)]
    _write_bm25_index(tmp_path, ids, tokenized)

    with patch("app.services.hybrid_search._QVAC_INGEST_DIR", tmp_path):
        results = bm25_search("bitcoin", "COURSE1", top_k=3)

    assert len(results) <= 3


# ---------------------------------------------------------------------------
# rrf_fuse
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_rrf_fuse_empty_inputs_return_empty():
    result = rrf_fuse([], [], {}, top_k=5)
    assert result == []


@pytest.mark.unit
def test_rrf_fuse_dense_only_returns_all():
    dense = [_make_evidence_chunk("c1"), _make_evidence_chunk("c2")]
    result = rrf_fuse(dense, [], {}, top_k=10)
    ids = [c.chunk_id for c in result]
    assert "c1" in ids
    assert "c2" in ids


@pytest.mark.unit
def test_rrf_fuse_shared_id_ranks_first():
    dense = [_make_evidence_chunk("shared", 0.9), _make_evidence_chunk("dense_only", 0.5)]
    bm25_hits = [("shared", 2.5), ("bm25_only", 1.0)]
    corpus = {
        "bm25_only": {"text": "BM25 text", "doc_id": "D", "label": "p.1",
                      "page": 1, "section": ""}
    }
    result = rrf_fuse(dense, bm25_hits, corpus, top_k=10)
    assert result[0].chunk_id == "shared"


@pytest.mark.unit
def test_rrf_fuse_respects_top_k():
    dense = [_make_evidence_chunk(f"d{i}") for i in range(10)]
    bm25_hits = [(f"b{i}", float(10 - i)) for i in range(10)]
    corpus = {
        f"b{i}": {"text": f"BM25 text {i}", "doc_id": "D", "label": "p.1",
                  "page": 1, "section": ""}
        for i in range(10)
    }
    result = rrf_fuse(dense, bm25_hits, corpus, top_k=5)
    assert len(result) == 5


@pytest.mark.unit
def test_rrf_fuse_bm25_only_chunks_reconstructed_from_corpus():
    # Only BM25 hit, not in dense_chunks
    bm25_hits = [("bm25_only", 3.0)]
    corpus = {
        "bm25_only": {
            "text": "BM25-only content",
            "doc_id": "DOC1",
            "label": "p. 5",
            "page": 5,
            "section": "Mining",
        }
    }
    result = rrf_fuse([], bm25_hits, corpus, top_k=5)
    assert len(result) == 1
    assert result[0].chunk_id == "bm25_only"
    assert result[0].text == "BM25-only content"
    assert result[0].anchor.page == 5


@pytest.mark.unit
def test_rrf_fuse_scores_updated_to_rrf_value():
    dense = [_make_evidence_chunk("c1", score=0.99)]
    result = rrf_fuse(dense, [], {}, top_k=5)
    # RRF score is much smaller than cosine similarity
    assert result[0].score < 0.1


@pytest.mark.unit
def test_rrf_fuse_bm25_rank_order_preserved():
    bm25_hits = [("b1", 5.0), ("b2", 3.0)]
    corpus = {
        "b1": {"text": "B1", "doc_id": "D", "label": "p.1", "page": 1, "section": ""},
        "b2": {"text": "B2", "doc_id": "D", "label": "p.2", "page": 2, "section": ""},
    }
    result = rrf_fuse([], bm25_hits, corpus, top_k=10)
    ids = [c.chunk_id for c in result]
    assert ids.index("b1") < ids.index("b2")
