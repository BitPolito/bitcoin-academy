"""Unit tests for app.rag.compressor.

All QVAC HTTP calls are mocked; no external service needed.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _is_enabled
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_is_enabled_false_when_rag_compress_context_unset(monkeypatch):
    monkeypatch.delenv("RAG_COMPRESS_CONTEXT", raising=False)
    # Re-import to pick up env change
    import importlib
    import app.rag.compressor as mod
    importlib.reload(mod)
    assert not mod._is_enabled()


@pytest.mark.unit
def test_is_enabled_false_when_qvac_llm_disabled(monkeypatch):
    monkeypatch.setenv("RAG_COMPRESS_CONTEXT", "true")
    monkeypatch.setenv("QVAC_LLM_ENABLED", "false")
    import importlib
    import app.rag.compressor as mod
    importlib.reload(mod)
    assert not mod._is_enabled()
    # cleanup
    monkeypatch.setenv("QVAC_LLM_ENABLED", "true")


@pytest.mark.unit
def test_is_enabled_true_when_all_conditions_met(monkeypatch):
    monkeypatch.setenv("RAG_COMPRESS_CONTEXT", "true")
    monkeypatch.setenv("QVAC_LLM_ENABLED", "true")
    monkeypatch.setenv("QVAC_SERVICE_URL", "http://localhost:3001")
    import importlib
    import app.rag.compressor as mod
    importlib.reload(mod)
    assert mod._is_enabled()


# ---------------------------------------------------------------------------
# compress_passages — disabled path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_compress_passages_returns_originals_when_disabled():
    from app.rag import compressor
    with patch.object(compressor, "_is_enabled", return_value=False):
        passages = ["passage A", "passage B"]
        result = compressor.compress_passages("query", passages)
    assert result == passages


@pytest.mark.unit
def test_compress_passages_returns_empty_for_empty_input():
    from app.rag import compressor
    with patch.object(compressor, "_is_enabled", return_value=True):
        result = compressor.compress_passages("query", [])
    assert result == []


# ---------------------------------------------------------------------------
# _compress_one — QVAC path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_compress_one_returns_compressed_on_success():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answer": "Relevant sentence only."}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.rag.compressor.httpx.post", return_value=mock_resp):
        from app.rag.compressor import _compress_one
        result = _compress_one("What is Bitcoin?", "Bitcoin is P2P cash. Also some unrelated text.")

    assert result == "Relevant sentence only."


@pytest.mark.unit
def test_compress_one_returns_original_when_qvac_says_not_relevant():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answer": "<not_relevant>"}
    mock_resp.raise_for_status = MagicMock()

    original = "Unrelated content."
    with patch("app.rag.compressor.httpx.post", return_value=mock_resp):
        from app.rag.compressor import _compress_one
        result = _compress_one("What is mining?", original)

    assert result == original


@pytest.mark.unit
def test_compress_one_returns_original_on_http_error():
    import httpx
    original = "Some passage text."
    with patch("app.rag.compressor.httpx.post", side_effect=httpx.ConnectError("refused")):
        from app.rag.compressor import _compress_one
        result = _compress_one("question", original)

    assert result == original


@pytest.mark.unit
def test_compress_one_passes_system_prompt_to_qvac():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answer": "compressed"}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.rag.compressor.httpx.post", return_value=mock_resp) as mock_post:
        from app.rag.compressor import _compress_one, _COMPRESS_SYSTEM_PROMPT
        _compress_one("query", "passage text")

    payload = mock_post.call_args[1]["json"]
    assert payload["systemPrompt"] == _COMPRESS_SYSTEM_PROMPT
    assert payload["question"] == "query"
    assert payload["context"][0]["text"] == "passage text"


# ---------------------------------------------------------------------------
# compress_passages — parallel execution
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_compress_passages_returns_all_results_on_success():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    call_count = [0]
    def make_resp(url, **kwargs):
        call_count[0] += 1
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = {"answer": f"compressed_{call_count[0]}"}
        return r

    from app.rag import compressor
    with patch.object(compressor, "_is_enabled", return_value=True), \
         patch("app.rag.compressor.httpx.post", side_effect=make_resp):
        result = compressor.compress_passages("query", ["p1", "p2", "p3"])

    assert len(result) == 3
    assert all(r.startswith("compressed_") for r in result)


@pytest.mark.unit
def test_compress_passages_falls_back_per_passage_on_error():
    """A failure on one passage should not affect others."""
    import httpx as _httpx

    call_count = [0]
    originals = ["passage_A", "passage_B", "passage_C"]

    def make_resp(url, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise _httpx.ConnectError("refused")
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = {"answer": f"ok_{call_count[0]}"}
        return r

    from app.rag import compressor
    with patch.object(compressor, "_is_enabled", return_value=True), \
         patch("app.rag.compressor.httpx.post", side_effect=make_resp):
        result = compressor.compress_passages("query", originals)

    # Failed passage falls back to original; others are compressed
    assert len(result) == 3
    assert originals[1] in result  # fallback preserved
