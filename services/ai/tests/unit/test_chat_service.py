"""Unit tests for app.services.chat_service.

Covers the async answer() function.
Retrieval pipeline and LLM generation are mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.chat_service import ChatResult, Citation
from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(chunk_id: str = "DOC1_p0000_c0000", text: str = "Bitcoin text.",
                score: float = 0.9) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=text,
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


def _mock_httpx_response(json_data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# answer() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_happy_path_returns_chat_result():
    ev_chunk = _make_chunk()
    generate_resp = _mock_httpx_response({"answer": "Bitcoin is a P2P currency."})

    with patch("app.services.chat_service.unified_retrieval", new_callable=AsyncMock) as mock_retrieval, \
         patch("app.services.chat_service._client") as mock_client, \
         patch("app.rag.compressor.compress_passages", return_value=["Compressed text"]), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):

        # Mock the new unified pipeline returning (context_chunks, reranked)
        mock_retrieval.return_value = ([ev_chunk], [ev_chunk])
        mock_client.post = AsyncMock(return_value=generate_resp)

        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    assert isinstance(result, ChatResult)
    assert result.answer == "Bitcoin is a P2P currency."
    assert result.retrieval_used is True
    assert len(result.citations) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_fallback_on_retrieve_error():
    with patch("app.services.chat_service.unified_retrieval", new_callable=AsyncMock) as mock_retrieval, \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):
        
        # Simulate the unified pipeline raising an HTTP error (both QVAC and Chroma failed)
        mock_retrieval.side_effect = httpx.HTTPError("error")

        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    assert result.retrieval_used is False
    assert result.citations == []
    assert "non è disponibile" in result.answer


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_generate_failure_returns_first_context_block():
    ev_chunk = _make_chunk(text="First context block text.")
    gen_error = httpx.ConnectError("refused")

    with patch("app.services.chat_service.unified_retrieval", new_callable=AsyncMock) as mock_retrieval, \
         patch("app.services.chat_service._client") as mock_client, \
         patch("app.rag.compressor.compress_passages", return_value=["First context block text."]), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):

        mock_retrieval.return_value = ([ev_chunk], [ev_chunk])
        mock_client.post = AsyncMock(side_effect=gen_error)
        
        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    assert "First context block text." in result.answer


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_citations_use_child_chunks():
    child = _make_chunk(text="Child text for citation.", score=0.7)
    parent = _make_chunk(text="Full parent context block, much longer.", score=0.7)

    generate_resp = _mock_httpx_response({"answer": "Answer."})

    with patch("app.services.chat_service.unified_retrieval", new_callable=AsyncMock) as mock_retrieval, \
         patch("app.services.chat_service._client") as mock_client, \
         patch("app.rag.compressor.compress_passages", return_value=["Full parent text"]), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):

        # unified_retrieval returns (context_chunks, reranked_citations)
        mock_retrieval.return_value = ([parent], [child])
        mock_client.post = AsyncMock(return_value=generate_resp)
        
        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    # Citations come from reranked (child), not context_chunks (parent)
    assert result.citations[0].snippet == "Child text for citation."[:200]