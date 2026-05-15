"""Unit tests for app.services.study_service.

Covers _parse_citations(), _generate(), _route() with/without rag_only, and dispatch().
All QVAC HTTP calls are mocked; no external services needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk, EvidencePack
from app.schemas.study_schemas import StudyAction
from app.services.study_service import (
    DispatchResult,
    SourceChunk,
    _parse_citations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(chunk_id: str = "c1", text: str = "Bitcoin is peer-to-peer cash.",
                score: float = 0.9) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        anchor=CitationAnchor(
            doc_id="DOC1",
            doc_name="whitepaper.pdf",
            section="Intro",
            page=1,
            slide=None,
            chunk_id=chunk_id,
            chunk_type="paragraph",
        ),
    )


def _make_pack(chunks: list[EvidenceChunk] | None = None, query: str = "What is Bitcoin?") -> EvidencePack:
    _chunks = chunks or [_make_chunk("c1"), _make_chunk("c2", text="Mining secures the chain.")]
    return EvidencePack(
        query=query,
        action="explain",
        chunks=_chunks,
        total_candidates=len(_chunks),
        ordering=list(range(len(_chunks))),
        deduped_passages=[c.text for c in _chunks],
    )


def _make_httpx_resp(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _parse_citations
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_citations_extracts_referenced_chunks():
    pack = _make_pack()
    text = "Bitcoin [ref_1] was described in 2008. Mining [ref_2] keeps it secure."
    result = _parse_citations(text, pack)
    assert len(result) == 2
    assert result[0].snippet == pack.chunks[0].text
    assert result[1].snippet == pack.chunks[1].text


@pytest.mark.unit
def test_parse_citations_falls_back_to_all_when_no_markers():
    pack = _make_pack()
    text = "Bitcoin is interesting but no citations here."
    result = _parse_citations(text, pack)
    # No [ref_N] markers → all chunks returned
    assert len(result) == len(pack.chunks)


@pytest.mark.unit
def test_parse_citations_deduplicates_repeated_refs():
    pack = _make_pack()
    text = "[ref_1] is cited again in [ref_1]."
    result = _parse_citations(text, pack)
    assert len(result) == 1
    assert result[0].snippet == pack.chunks[0].text


@pytest.mark.unit
def test_parse_citations_ignores_out_of_range_refs():
    pack = _make_pack()
    text = "See [ref_99] for details."  # out of range
    result = _parse_citations(text, pack)
    # Falls back to all chunks (no valid ref found)
    assert len(result) == len(pack.chunks)


@pytest.mark.unit
def test_parse_citations_ref_is_one_based():
    chunks = [_make_chunk("c1", "First chunk."), _make_chunk("c2", "Second chunk.")]
    pack = _make_pack(chunks=chunks)
    text = "The second passage [ref_2] covers mining."
    result = _parse_citations(text, pack)
    assert len(result) == 1
    assert result[0].snippet == "Second chunk."


@pytest.mark.unit
def test_parse_citations_preserves_anchor_metadata():
    pack = _make_pack()
    text = "See [ref_1]."
    result = _parse_citations(text, pack)
    src = result[0]
    assert src.label == "whitepaper.pdf"
    assert src.page == 1
    assert src.doc_id == "DOC1"


# ---------------------------------------------------------------------------
# _generate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_calls_qvac_generate_endpoint():
    resp = _make_httpx_resp({"answer": "Bitcoin uses proof-of-work."})
    with patch("app.services.study_service._qvac_client") as mock_client:
        mock_client.post = AsyncMock(return_value=resp)
        from app.services.study_service import _generate
        result = await _generate(StudyAction.EXPLAIN, "What is PoW?", "[ref_1] context text")

    mock_client.post.assert_awaited_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/generate"
    payload = call_args[1]["json"]
    assert payload["question"] == "What is PoW?"
    assert payload["context"][0]["text"] == "[ref_1] context text"
    assert "systemPrompt" in payload
    assert result == "Bitcoin uses proof-of-work."


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_passes_action_specific_system_prompt():
    resp = _make_httpx_resp({"answer": "Q1..."})
    with patch("app.services.study_service._qvac_client") as mock_client:
        mock_client.post = AsyncMock(return_value=resp)
        from app.services.study_service import _generate, _SYSTEM_PROMPTS
        await _generate(StudyAction.QUIZ, "Quiz me.", "some context")

    payload = mock_client.post.call_args[1]["json"]
    assert payload["systemPrompt"] == _SYSTEM_PROMPTS[StudyAction.QUIZ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_returns_none_on_qvac_http_error():
    import httpx
    with patch("app.services.study_service._qvac_client") as mock_client:
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        from app.services.study_service import _generate
        result = await _generate(StudyAction.EXPLAIN, "question", "context")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_returns_none_on_empty_answer():
    resp = _make_httpx_resp({"answer": ""})
    with patch("app.services.study_service._qvac_client") as mock_client:
        mock_client.post = AsyncMock(return_value=resp)
        from app.services.study_service import _generate
        result = await _generate(StudyAction.EXPLAIN, "question", "context")

    assert result is None


# ---------------------------------------------------------------------------
# _route with rag_only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_route_rag_only_skips_generation():
    pack = _make_pack()
    with patch("app.services.study_service._retrieve", new_callable=AsyncMock, return_value=("raw", pack)), \
         patch("app.services.study_service._generate", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.study_service.DispatchTrace") as _trace:
        trace = MagicMock()
        from app.services.study_service import _route, StudyAction
        result = await _route("What is Bitcoin?", "COURSE1", StudyAction.EXPLAIN, trace, rag_only=True)

    mock_gen.assert_not_called()
    assert isinstance(result, DispatchResult)
    assert result.retrieval_used is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_route_rag_only_answer_is_context_block():
    pack = _make_pack()
    expected_block = pack.context_block()
    with patch("app.services.study_service._retrieve", new_callable=AsyncMock, return_value=("raw", pack)):
        trace = MagicMock()
        from app.services.study_service import _route
        result = await _route("Q", "COURSE1", StudyAction.EXPLAIN, trace, rag_only=True)

    assert result.answer == expected_block


@pytest.mark.asyncio
@pytest.mark.unit
async def test_route_rag_only_false_calls_generation():
    pack = _make_pack()
    with patch("app.services.study_service._retrieve", new_callable=AsyncMock, return_value=("", pack)), \
         patch("app.services.study_service._generate", new_callable=AsyncMock, return_value="Generated answer.") as mock_gen:
        trace = MagicMock()
        from app.services.study_service import _route
        result = await _route("Q", "COURSE1", StudyAction.EXPLAIN, trace, rag_only=False)

    mock_gen.assert_awaited_once()
    assert result.answer == "Generated answer."


@pytest.mark.asyncio
@pytest.mark.unit
async def test_route_retrieve_action_never_calls_generation():
    pack = _make_pack()
    with patch("app.services.study_service._retrieve", new_callable=AsyncMock, return_value=("raw", pack)), \
         patch("app.services.study_service._generate", new_callable=AsyncMock) as mock_gen:
        trace = MagicMock()
        from app.services.study_service import _route
        await _route("Q", "COURSE1", StudyAction.RETRIEVE, trace, rag_only=False)

    mock_gen.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_route_generation_fallback_on_none():
    pack = _make_pack()
    with patch("app.services.study_service._retrieve", new_callable=AsyncMock, return_value=("raw answer", pack)), \
         patch("app.services.study_service._generate", new_callable=AsyncMock, return_value=None):
        trace = MagicMock()
        from app.services.study_service import _route
        result = await _route("Q", "COURSE1", StudyAction.EXPLAIN, trace, rag_only=False)

    assert result.answer == "raw answer"


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_dispatch_rag_only_propagated():
    pack = _make_pack()
    with patch("app.services.study_service._route", new_callable=AsyncMock,
               return_value=DispatchResult(answer="ok", citations=[], retrieval_used=True)) as mock_route, \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"):
        from app.services.study_service import dispatch
        await dispatch("What is Bitcoin?", "COURSE1", StudyAction.EXPLAIN, rag_only=True)

    _, call_kwargs = mock_route.call_args
    assert call_kwargs.get("rag_only") is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_dispatch_rejects_short_query():
    from app.services.study_service import dispatch
    with pytest.raises(ValueError, match="too short"):
        await dispatch("abc", "COURSE1", StudyAction.EXPLAIN)
