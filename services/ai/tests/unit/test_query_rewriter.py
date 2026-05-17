"""Unit tests for app.rag.query_rewriter.

All QVAC HTTP calls are mocked via httpx; no external service needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_qvac_resp(answer: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"answer": answer}
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# expand_query — disabled paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_returns_original_when_no_flag_set():
    from app.rag import query_rewriter
    with patch.object(query_rewriter, "_is_enabled", return_value=False):
        result = await query_rewriter.expand_query("What is Bitcoin?")
    assert result == "What is Bitcoin?"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_returns_original_when_qvac_llm_disabled(monkeypatch):
    monkeypatch.setenv("QVAC_LLM_ENABLED", "false")
    monkeypatch.setenv("RAG_HYDE", "true")
    import importlib
    import app.rag.query_rewriter as mod
    importlib.reload(mod)

    result = await mod.expand_query("What is Bitcoin?")
    assert result == "What is Bitcoin?"
    # cleanup
    monkeypatch.setenv("QVAC_LLM_ENABLED", "true")


# ---------------------------------------------------------------------------
# expand_query — HyDE path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_hyde_returns_generated_passage():
    generated = "Bitcoin is a decentralised currency invented by Satoshi Nakamoto in 2008."
    with patch("app.rag.query_rewriter._call_qvac", new_callable=AsyncMock, return_value=generated) as mock_call:
        from app.rag import query_rewriter
        with patch.object(query_rewriter, "_is_enabled", return_value=True), \
             patch.object(query_rewriter, "_HYDE_ENABLED", True):
            result = await query_rewriter.expand_query("What is Bitcoin?")

    assert result == generated


@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_hyde_uses_hyde_system_prompt():
    with patch("app.rag.query_rewriter._call_qvac", new_callable=AsyncMock, return_value="passage") as mock_call:
        from app.rag import query_rewriter
        with patch.object(query_rewriter, "_is_enabled", return_value=True), \
             patch.object(query_rewriter, "_HYDE_ENABLED", True):
            await query_rewriter.expand_query("What is Bitcoin?")

    call_args = mock_call.call_args[0]
    assert call_args[0] == query_rewriter._HYDE_SYSTEM_PROMPT


@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_hyde_falls_back_to_original_on_none():
    with patch("app.rag.query_rewriter._call_qvac", new_callable=AsyncMock, return_value=None):
        from app.rag import query_rewriter
        with patch.object(query_rewriter, "_is_enabled", return_value=True), \
             patch.object(query_rewriter, "_HYDE_ENABLED", True), \
             patch.object(query_rewriter, "_REWRITE_ENABLED", False):
            result = await query_rewriter.expand_query("What is Bitcoin?")

    assert result == "What is Bitcoin?"


# ---------------------------------------------------------------------------
# expand_query — rewrite path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_rewrite_returns_rewritten_query():
    rewritten = "Bitcoin peer-to-peer electronic cash system"
    with patch("app.rag.query_rewriter._call_qvac", new_callable=AsyncMock, return_value=rewritten):
        from app.rag import query_rewriter
        with patch.object(query_rewriter, "_is_enabled", return_value=True), \
             patch.object(query_rewriter, "_HYDE_ENABLED", False), \
             patch.object(query_rewriter, "_REWRITE_ENABLED", True):
            result = await query_rewriter.expand_query("Can you tell me about Bitcoin?")

    assert result == rewritten


@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_rewrite_uses_rewrite_system_prompt():
    with patch("app.rag.query_rewriter._call_qvac", new_callable=AsyncMock, return_value="rewritten") as mock_call:
        from app.rag import query_rewriter
        with patch.object(query_rewriter, "_is_enabled", return_value=True), \
             patch.object(query_rewriter, "_HYDE_ENABLED", False), \
             patch.object(query_rewriter, "_REWRITE_ENABLED", True):
            await query_rewriter.expand_query("question")

    call_args = mock_call.call_args[0]
    assert call_args[0] == query_rewriter._REWRITE_SYSTEM_PROMPT


@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_rewrite_falls_back_to_original_on_none():
    with patch("app.rag.query_rewriter._call_qvac", new_callable=AsyncMock, return_value=None):
        from app.rag import query_rewriter
        with patch.object(query_rewriter, "_is_enabled", return_value=True), \
             patch.object(query_rewriter, "_HYDE_ENABLED", False), \
             patch.object(query_rewriter, "_REWRITE_ENABLED", True):
            result = await query_rewriter.expand_query("original query")

    assert result == "original query"


# ---------------------------------------------------------------------------
# expand_query — HyDE takes precedence over rewrite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_expand_query_hyde_takes_precedence_over_rewrite():
    """When both flags are set, HyDE runs first and rewrite is skipped if HyDE succeeds."""
    hyde_result = "Hypothetical document passage."
    call_log: list[str] = []

    async def fake_call(system_prompt: str, question: str):
        call_log.append(system_prompt)
        return hyde_result

    with patch("app.rag.query_rewriter._call_qvac", side_effect=fake_call):
        from app.rag import query_rewriter
        with patch.object(query_rewriter, "_is_enabled", return_value=True), \
             patch.object(query_rewriter, "_HYDE_ENABLED", True), \
             patch.object(query_rewriter, "_REWRITE_ENABLED", True):
            result = await query_rewriter.expand_query("question")

    assert result == hyde_result
    # Only HyDE prompt was used; rewrite prompt was never called
    assert len(call_log) == 1
    assert call_log[0] == query_rewriter._HYDE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# _call_qvac — QVAC no-LLM fallback detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_call_qvac_returns_none_on_no_llm_fallback():
    """QVAC returns 'Nessun contesto disponibile.' when no LLM is loaded — treat as failure."""
    mock_resp = _mock_qvac_resp("Nessun contesto disponibile.")

    async def fake_post(*args, **kwargs):
        return mock_resp

    with patch("app.rag.query_rewriter.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from app.rag.query_rewriter import _call_qvac
        result = await _call_qvac("system", "question")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_call_qvac_returns_none_on_http_error():
    import httpx

    with patch("app.rag.query_rewriter.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_cls.return_value = mock_client

        from app.rag.query_rewriter import _call_qvac
        result = await _call_qvac("system", "question")

    assert result is None
