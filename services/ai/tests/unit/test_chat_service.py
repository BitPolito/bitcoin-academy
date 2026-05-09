"""Unit tests for app.services.chat_service — pure-logic helpers.

No network calls or DB connections are needed for these tests.
BM25 tests are skipped automatically if rank_bm25 is not installed.
"""
import json
import pickle
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.chat_service import _rrf_merge, _resolve_merged


# ---------------------------------------------------------------------------
# _rrf_merge
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_rrf_merge_empty_inputs_return_empty():
    assert _rrf_merge([], [], top_n=5) == []


@pytest.mark.unit
def test_rrf_merge_dense_only_returns_all_ids():
    dense = [{"chunk_id": "c1"}, {"chunk_id": "c2"}]
    result = _rrf_merge(dense, [], top_n=10)
    assert "c1" in result
    assert "c2" in result


@pytest.mark.unit
def test_rrf_merge_bm25_only_preserves_rank_order():
    bm25 = [
        {"chunk_id": "b1", "score": 0.9},
        {"chunk_id": "b2", "score": 0.5},
    ]
    result = _rrf_merge([], bm25, top_n=10)
    assert result.index("b1") < result.index("b2")


@pytest.mark.unit
def test_rrf_merge_shared_id_ranks_first():
    dense = [{"chunk_id": "shared"}, {"chunk_id": "dense_only"}]
    bm25 = [{"chunk_id": "shared", "score": 0.9}, {"chunk_id": "bm25_only", "score": 0.5}]
    result = _rrf_merge(dense, bm25, top_n=10)
    assert result[0] == "shared"


@pytest.mark.unit
def test_rrf_merge_respects_top_n():
    dense = [{"chunk_id": f"d{i}"} for i in range(20)]
    bm25 = [{"chunk_id": f"b{i}", "score": 0.5} for i in range(20)]
    result = _rrf_merge(dense, bm25, top_n=7)
    assert len(result) == 7


@pytest.mark.unit
def test_rrf_merge_skips_empty_chunk_id():
    dense = [{"chunk_id": ""}, {"chunk_id": "c1"}, {}]
    result = _rrf_merge(dense, [], top_n=5)
    assert "" not in result
    assert "c1" in result


@pytest.mark.unit
def test_rrf_merge_deduplicates_ids():
    dense = [{"chunk_id": "c1"}, {"chunk_id": "c1"}]  # duplicate
    bm25 = [{"chunk_id": "c1", "score": 0.8}]
    result = _rrf_merge(dense, bm25, top_n=10)
    assert result.count("c1") == 1


# ---------------------------------------------------------------------------
# _resolve_merged
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_resolve_merged_uses_dense_registry():
    registry = {
        "c1": {"chunk_id": "c1", "content": "Dense C1", "score": 0.9},
        "c2": {"chunk_id": "c2", "content": "Dense C2", "score": 0.8},
    }
    result = _resolve_merged(["c1", "c2"], registry, "COURSE1")
    assert len(result) == 2
    assert result[0]["content"] == "Dense C1"
    assert result[1]["content"] == "Dense C2"


@pytest.mark.unit
def test_resolve_merged_preserves_merged_order():
    registry = {
        "c1": {"chunk_id": "c1", "content": "C1"},
        "c2": {"chunk_id": "c2", "content": "C2"},
        "c3": {"chunk_id": "c3", "content": "C3"},
    }
    result = _resolve_merged(["c3", "c1", "c2"], registry, "COURSE1")
    assert [r["content"] for r in result] == ["C3", "C1", "C2"]


@pytest.mark.unit
def test_resolve_merged_falls_back_to_corpus_for_bm25_only(tmp_path):
    corpus = {
        "bm25_only": {
            "text": "BM25-only content",
            "label": "p. 5",
            "page": 5,
            "section": "Mining",
            "doc_id": "DOC1",
            "parent_id": "DOC1_p0000",
        }
    }
    (tmp_path / "COURSE1_corpus.json").write_text(json.dumps(corpus))

    with patch("app.services.chat_service._QVAC_INGEST_DIR", tmp_path):
        result = _resolve_merged(["bm25_only"], {}, "COURSE1")

    assert len(result) == 1
    assert result[0]["content"] == "BM25-only content"
    assert result[0]["chunk_id"] == "bm25_only"
    assert result[0]["page"] == 5


@pytest.mark.unit
def test_resolve_merged_mixes_dense_and_corpus(tmp_path):
    corpus = {
        "bm25_id": {
            "text": "Corpus text",
            "label": "p. 2",
            "page": 2,
            "section": "",
            "doc_id": "DOC1",
            "parent_id": "",
        }
    }
    (tmp_path / "COURSE1_corpus.json").write_text(json.dumps(corpus))

    registry = {"dense_id": {"chunk_id": "dense_id", "content": "Dense text", "score": 0.9}}

    with patch("app.services.chat_service._QVAC_INGEST_DIR", tmp_path):
        result = _resolve_merged(["dense_id", "bm25_id"], registry, "COURSE1")

    assert len(result) == 2
    assert result[0]["content"] == "Dense text"
    assert result[1]["content"] == "Corpus text"


@pytest.mark.unit
def test_resolve_merged_skips_unknown_ids(tmp_path):
    (tmp_path / "COURSE1_corpus.json").write_text("{}")
    with patch("app.services.chat_service._QVAC_INGEST_DIR", tmp_path):
        result = _resolve_merged(["unknown_id"], {}, "COURSE1")
    assert result == []


# ---------------------------------------------------------------------------
# _bm25_search
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_bm25_search_returns_empty_for_empty_ingest_dir():
    from app.services.chat_service import _bm25_search
    with patch("app.services.chat_service._QVAC_INGEST_DIR", Path("")):
        result = _bm25_search("bitcoin", "COURSE1")
    assert result == []


@pytest.mark.unit
def test_bm25_search_returns_empty_when_pkl_missing(tmp_path):
    from app.services.chat_service import _bm25_search
    with patch("app.services.chat_service._QVAC_INGEST_DIR", tmp_path):
        result = _bm25_search("bitcoin", "NO_SUCH_COURSE")
    assert result == []


@pytest.mark.unit
def test_bm25_search_returns_ranked_results(tmp_path):
    pytest.importorskip("rank_bm25")
    from rank_bm25 import BM25Okapi
    from app.services.chat_service import _bm25_search

    ids = ["chunk_bitcoin", "chunk_mining"]
    tokenized = [["bitcoin", "utxo", "transaction"], ["proof", "work", "mining", "hash"]]
    bm25 = BM25Okapi(tokenized)
    with (tmp_path / "COURSE1_bm25.pkl").open("wb") as f:
        pickle.dump({"ids": ids, "bm25": bm25}, f)

    with patch("app.services.chat_service._QVAC_INGEST_DIR", tmp_path):
        results = _bm25_search("bitcoin utxo transaction", "COURSE1", top_k=5)

    assert len(results) > 0
    assert all("chunk_id" in r and "score" in r for r in results)
    assert results[0]["chunk_id"] == "chunk_bitcoin"


@pytest.mark.unit
def test_bm25_search_zero_score_excluded(tmp_path):
    pytest.importorskip("rank_bm25")
    from rank_bm25 import BM25Okapi
    from app.services.chat_service import _bm25_search

    ids = ["relevant", "irrelevant"]
    tokenized = [["bitcoin", "utxo"], ["astronomy", "stars"]]
    bm25 = BM25Okapi(tokenized)
    with (tmp_path / "COURSE1_bm25.pkl").open("wb") as f:
        pickle.dump({"ids": ids, "bm25": bm25}, f)

    with patch("app.services.chat_service._QVAC_INGEST_DIR", tmp_path):
        results = _bm25_search("bitcoin", "COURSE1", top_k=10)

    chunk_ids = [r["chunk_id"] for r in results]
    assert "irrelevant" not in chunk_ids
