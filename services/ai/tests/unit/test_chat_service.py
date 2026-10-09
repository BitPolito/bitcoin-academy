"""Unit tests for app.services.chat_service.

Covers _qvac_dict_to_chunk() and the async answer() function.
All network calls, hybrid_search, reranker, and parent_expansion are mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chat_service import _qvac_dict_to_chunk, ChatResult, Citation
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


def _make_qvac_dict(chunk_id: str = "DOC1_p0000_c0000") -> dict:
    return {
        "chunk_id": chunk_id,
        "content": "Bitcoin uses UTXO.",
        "score": 0.85,
        "label": "Bitcoin Whitepaper",
        "page": 3,
        "slide": 0,
        "section": "Transactions",
        "doc_id": "DOC1",
        "parent_id": "DOC1_p0000",
    }


def _mock_httpx_response(json_data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


def _mock_httpx_error():
    import httpx
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.ConnectError("connection refused")
    return resp


# ---------------------------------------------------------------------------
# _qvac_dict_to_chunk
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_qvac_dict_to_chunk_maps_fields():
    d = _make_qvac_dict()
    chunk = _qvac_dict_to_chunk(d)
    assert chunk.chunk_id == "DOC1_p0000_c0000"
    assert chunk.text == "Bitcoin uses UTXO."
    assert chunk.score == 0.85
    assert chunk.anchor.doc_name == "Bitcoin Whitepaper"
    assert chunk.anchor.page == 3
    assert chunk.anchor.doc_id == "DOC1"
    assert chunk.anchor.section == "Transactions"


@pytest.mark.unit
def test_qvac_dict_to_chunk_slide_zero_becomes_none():
    d = {**_make_qvac_dict(), "slide": 0}
    chunk = _qvac_dict_to_chunk(d)
    assert chunk.anchor.slide is None


@pytest.mark.unit
def test_qvac_dict_to_chunk_page_zero_becomes_none():
    d = {**_make_qvac_dict(), "page": 0}
    chunk = _qvac_dict_to_chunk(d)
    assert chunk.anchor.page is None


@pytest.mark.unit
def test_qvac_dict_to_chunk_empty_section_becomes_none():
    d = {**_make_qvac_dict(), "section": ""}
    chunk = _qvac_dict_to_chunk(d)
    assert chunk.anchor.section is None


@pytest.mark.unit
def test_qvac_dict_to_chunk_uses_content_key():
    d = {"chunk_id": "c1", "content": "Dense content.", "text": "Should not use this.",
         "score": 0.5, "label": "", "page": 0, "slide": 0, "section": "", "doc_id": ""}
    chunk = _qvac_dict_to_chunk(d)
    assert chunk.text == "Dense content."


@pytest.mark.unit
def test_qvac_dict_to_chunk_falls_back_to_text_key():
    d = {"chunk_id": "c1", "content": "", "text": "Fallback text.",
         "score": 0.5, "label": "", "page": 0, "slide": 0, "section": "", "doc_id": ""}
    chunk = _qvac_dict_to_chunk(d)
    assert chunk.text == "Fallback text."


# ---------------------------------------------------------------------------
# answer() — happy path with hybrid search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_happy_path_returns_chat_result():
    chunk_dict = _make_qvac_dict()
    ev_chunk = _make_chunk()
    bm25_hits = [("DOC1_p0000_c0000", 2.5)]
    corpus = {"DOC1_p0000_c0000": {"text": "BM25 text", "doc_id": "DOC1"}}

    retrieve_resp = _mock_httpx_response({"chunks": [chunk_dict]})
    generate_resp = _mock_httpx_response({"answer": "Bitcoin is a P2P currency."})

    with patch("app.services.chat_service._client") as mock_client, \
         patch("app.services.hybrid_search.bm25_search", return_value=bm25_hits), \
         patch("app.services.hybrid_search.load_bm25_index", return_value=(None, None, corpus)), \
         patch("app.services.hybrid_search.rrf_fuse", return_value=[ev_chunk]), \
         patch("app.services.reranker.rerank", return_value=[ev_chunk]), \
         patch("app.services.parent_expansion.expand_to_parents", return_value=[ev_chunk]), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):

        mock_client.post = AsyncMock(side_effect=[retrieve_resp, generate_resp])
        result = await __import__("app.services.chat_service", fromlist=["answer"]).answer(
            "What is Bitcoin?", "COURSE1"
        )

    assert isinstance(result, ChatResult)
    assert result.answer == "Bitcoin is a P2P currency."
    assert result.retrieval_used is True
    assert len(result.citations) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_dense_only_when_no_bm25():
    chunk_dict = _make_qvac_dict()
    ev_chunk = _make_chunk()

    retrieve_resp = _mock_httpx_response({"chunks": [chunk_dict]})
    generate_resp = _mock_httpx_response({"answer": "Mining secures the chain."})

    with patch("app.services.chat_service._client") as mock_client, \
         patch("app.services.hybrid_search.bm25_search", return_value=[]), \
         patch("app.services.hybrid_search.rrf_fuse") as mock_rrf, \
         patch("app.services.reranker.rerank", return_value=[ev_chunk]), \
         patch("app.services.parent_expansion.expand_to_parents", return_value=[ev_chunk]):

        mock_client.post = AsyncMock(side_effect=[retrieve_resp, generate_resp])
        from app.services.chat_service import answer
        result = await answer("What is mining?", "COURSE1")

    # rrf_fuse must NOT be called when BM25 has no results
    mock_rrf.assert_not_called()
    assert result.answer == "Mining secures the chain."


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_chroma_fallback_on_retrieve_error():
    import httpx

    with patch("app.services.chat_service._client") as mock_client, \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    assert result.retrieval_used is False
    assert result.citations == []
    assert len(result.answer) > 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_chroma_fallback_on_zero_chunks():
    retrieve_resp = _mock_httpx_response({"chunks": []})
    generate_resp = _mock_httpx_response({"answer": "No relevant content found."})

    with patch("app.services.chat_service._client") as mock_client, \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):
        mock_client.post = AsyncMock(side_effect=[retrieve_resp, generate_resp])
        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    assert result.retrieval_used is False
    assert result.citations == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_generate_failure_returns_first_context_block():
    import httpx

    chunk_dict = _make_qvac_dict()
    ev_chunk = _make_chunk(text="First context block text.")

    retrieve_resp = _mock_httpx_response({"chunks": [chunk_dict]})
    gen_error = httpx.ConnectError("refused")

    with patch("app.services.chat_service._client") as mock_client, \
         patch("app.services.hybrid_search.bm25_search", return_value=[]), \
         patch("app.services.reranker.rerank", return_value=[ev_chunk]), \
         patch("app.services.parent_expansion.expand_to_parents", return_value=[ev_chunk]), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):

        mock_post = AsyncMock(side_effect=[retrieve_resp, gen_error])
        mock_client.post = mock_post
        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    assert "First context block text." in result.answer


@pytest.mark.asyncio
@pytest.mark.unit
async def test_answer_citations_use_child_chunks():
    chunk_dict = _make_qvac_dict()
    child = _make_chunk(text="Child text for citation.", score=0.7)
    parent = _make_chunk(text="Full parent context block, much longer.", score=0.7)

    retrieve_resp = _mock_httpx_response({"chunks": [chunk_dict]})
    generate_resp = _mock_httpx_response({"answer": "Answer."})

    with patch("app.services.chat_service._client") as mock_client, \
         patch("app.services.hybrid_search.bm25_search", return_value=[]), \
         patch("app.services.reranker.rerank", return_value=[child]), \
         patch("app.services.parent_expansion.expand_to_parents", return_value=[parent]), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):

        mock_client.post = AsyncMock(side_effect=[retrieve_resp, generate_resp])
        from app.services.chat_service import answer
        result = await answer("What is Bitcoin?", "COURSE1")

    # Citations come from reranked (child), not context_chunks (parent)
    assert result.citations[0].snippet == "Child text for citation."[:200]
