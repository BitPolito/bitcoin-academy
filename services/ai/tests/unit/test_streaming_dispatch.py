"""SSE streaming paths — study_service.stream_dispatch and chat_service.stream_answer.

These were the least-covered code in the service layer (~53-54% on the coverage
audit) despite streaming being the primary interaction path for most study
actions. Every fallback here matters: a student watching a live response has
no way to tell "the model produced nothing" from "the network call never
returned" — both must degrade to the same buffered answer rather than hang
or emit an empty stream.

The QVAC client's `.stream()` is used as an async context manager, which is a
different mocking shape from `.post()` — `_FakeStream` below reproduces just
enough of httpx's `Response.aiter_lines()` contract to drive it.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas.study_schemas import StudyAction
from app.services import chat_service, study_service

_CITATIONS_SENTINEL = "\x00CITATIONS\x00"
COURSE_ID = "course-1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeStreamResponse:
    """Minimal stand-in for the httpx streaming response used by aiter_lines()."""

    def __init__(self, lines: list[str], status_error: Exception | None = None):
        self._lines = lines
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamContext:
    """Reproduces `async with client.stream(...) as resp:` for a fixed sequence
    of SSE lines, or raises on entry to simulate a connection failure."""

    def __init__(self, lines: list[str] | None = None, connect_error: Exception | None = None,
                 status_error: Exception | None = None):
        self._lines = lines or []
        self._connect_error = connect_error
        self._status_error = status_error

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        if self._connect_error:
            raise self._connect_error
        return _FakeStreamResponse(self._lines, self._status_error)

    async def __aexit__(self, *exc):
        return False


def _sse(token: str) -> str:
    return f"data: {json.dumps(token)}"


def _qvac_json_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


async def _drain(gen):
    return [chunk async for chunk in gen]


# ---------------------------------------------------------------------------
# study_service.stream_dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_dispatch_rejects_a_too_short_query():
    with pytest.raises(ValueError):
        await _drain(study_service.stream_dispatch("hi", COURSE_ID, StudyAction.EXPLAIN))


@pytest.mark.asyncio
async def test_stream_dispatch_serves_a_cache_hit_as_a_single_burst_without_retrieval():
    """A cache hit must short-circuit before any retrieval call — the whole
    point of the cache is to skip the expensive path entirely."""
    cached_payload = {"answer": "cached explanation", "citations": [{"snippet": "s"}]}

    retrieval_calls = []

    async def _fake_multi(*args, **kwargs):
        retrieval_calls.append(args)
        raise AssertionError("retrieval must not run on a cache hit")

    with patch("app.services.cache_service.get_cached", return_value=cached_payload), \
         patch("app.services.cache_service.set_cached"), \
         patch.object(study_service, "_retrieve_multi", side_effect=_fake_multi):
        chunks = await _drain(
            study_service.stream_dispatch("Explain proof of work", COURSE_ID, StudyAction.EXPLAIN)
        )

    assert chunks[0] == "cached explanation"
    assert chunks[1].startswith(_CITATIONS_SENTINEL)
    assert json.loads(chunks[1][len(_CITATIONS_SENTINEL):]) == cached_payload["citations"]
    assert retrieval_calls == []


@pytest.mark.asyncio
async def test_stream_dispatch_buffers_retrieve_action_instead_of_streaming():
    """RETRIEVE needs the full parsed chunk list, not a token stream — it must
    never call QVAC /stream even though it is not excluded by generation_required."""
    from app.schemas.evidence_pack import EvidencePack

    empty_pack = EvidencePack(
        query="q", action="retrieve", chunks=[], total_candidates=0,
        ordering=[], deduped_passages=[],
    )
    stream_calls = []

    async def _fake_stream_generate(*args, **kwargs):
        stream_calls.append(args)
        yield "should not happen"

    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"), \
         patch.object(study_service, "_retrieve_multi", return_value=("", empty_pack)), \
         patch.object(study_service, "_stream_generate", side_effect=_fake_stream_generate):
        chunks = await _drain(
            study_service.stream_dispatch("What is a UTXO?", COURSE_ID, StudyAction.RETRIEVE)
        )

    assert stream_calls == []
    assert chunks[0] == "No relevant content found."


@pytest.mark.asyncio
async def test_stream_dispatch_yields_tokens_progressively_for_a_streaming_action():
    from app.schemas.evidence_pack import EvidencePack

    pack = EvidencePack(
        query="q", action="explain", chunks=[], total_candidates=0,
        ordering=[], deduped_passages=["source passage"],
    )

    async def _fake_stream_generate(*args, **kwargs):
        for tok in ["Bitcoin ", "uses ", "proof of work."]:
            yield tok

    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"), \
         patch.object(study_service, "_retrieve_multi", return_value=("", pack)), \
         patch.object(study_service, "_stream_generate", side_effect=_fake_stream_generate):
        chunks = await _drain(
            study_service.stream_dispatch("Explain proof of work", COURSE_ID, StudyAction.EXPLAIN)
        )

    assert chunks[:3] == ["Bitcoin ", "uses ", "proof of work."]
    assert chunks[-1].startswith(_CITATIONS_SENTINEL)


@pytest.mark.asyncio
async def test_stream_dispatch_falls_back_to_buffered_generate_when_the_stream_yields_nothing():
    """QVAC /stream returning zero tokens (connection dropped, empty response)
    must not leave the student staring at a blank answer."""
    from app.schemas.evidence_pack import EvidencePack

    pack = EvidencePack(
        query="q", action="explain", chunks=[], total_candidates=0,
        ordering=[], deduped_passages=["source passage"],
    )

    async def _empty_stream(*args, **kwargs):
        return
        yield  # pragma: no cover — makes this an async generator

    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"), \
         patch.object(study_service, "_retrieve_multi", return_value=("", pack)), \
         patch.object(study_service, "_stream_generate", side_effect=_empty_stream), \
         patch.object(study_service, "_generate", new=AsyncMock(return_value="buffered fallback")):
        chunks = await _drain(
            study_service.stream_dispatch("Explain proof of work", COURSE_ID, StudyAction.EXPLAIN)
        )

    assert chunks[0] == "buffered fallback"
    assert chunks[-1].startswith(_CITATIONS_SENTINEL)


@pytest.mark.asyncio
async def test_stream_dispatch_final_fallback_uses_raw_answer_not_the_evidence_pack():
    """Documents current, surprising behaviour rather than the intended one.

    When both the streaming and buffered generation paths fail, the final
    fallback is `raw_answer` — the bare string QVAC's own dense-retrieval call
    returned — not `pack.context_block()`. `dispatch()` has the identical
    branch (see `_route`'s `else: answer = raw_answer or "No relevant content
    found."`), so this is shared, existing behaviour, not new.

    The consequence: if `raw_answer` happens to be empty while `pack.chunks`
    holds real retrieved passages, the student sees "No relevant content
    found." even though evidence was retrieved and is sitting right there in
    the pack. That contradicts the graceful-degradation principle in
    docs/overview.md ("every study action still returns source passages").
    Tracked as a follow-up rather than fixed here, since this issue is about
    testing and reporting, not changing product behaviour.
    """
    from app.schemas.evidence_pack import EvidencePack, EvidenceChunk, CitationAnchor

    chunk = EvidenceChunk(
        chunk_id="c1", text="raw passage text", score=0.9,
        anchor=CitationAnchor(
            doc_id="d1", doc_name="doc.pdf", section=None, page=1,
            slide=None, chunk_id="c1", chunk_type="paragraph",
        ),
    )
    pack = EvidencePack(
        query="q", action="explain", chunks=[chunk], total_candidates=1,
        ordering=[0], deduped_passages=["raw passage text"],
    )
    assert pack.context_block(), "the pack does hold real, renderable evidence"

    async def _empty_stream(*args, **kwargs):
        return
        yield  # pragma: no cover

    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"), \
         patch.object(study_service, "_retrieve_multi", return_value=("", pack)), \
         patch.object(study_service, "_stream_generate", side_effect=_empty_stream), \
         patch.object(study_service, "_generate", new=AsyncMock(return_value=None)):
        chunks = await _drain(
            study_service.stream_dispatch("Explain proof of work", COURSE_ID, StudyAction.EXPLAIN)
        )

    # Current behaviour: the retrieved evidence is discarded here.
    assert chunks[0] == "No relevant content found."


# ---------------------------------------------------------------------------
# chat_service.stream_answer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_serves_a_cache_hit_without_calling_retrieval():
    cached_payload = {"answer": "cached chat answer", "citations": []}

    with patch("app.services.cache_service.get_cached", return_value=cached_payload), \
         patch("app.services.cache_service.set_cached"), \
         patch.object(chat_service, "_retrieve_and_rank", new=AsyncMock(
             side_effect=AssertionError("must not be called on a cache hit"))):
        chunks = await _drain(chat_service.stream_answer("What is Bitcoin?", COURSE_ID))

    assert chunks[0] == "cached chat answer"
    assert chunks[1].startswith("\x00CITATIONS\x00")


@pytest.mark.asyncio
async def test_chat_stream_reports_retrieval_failure_in_italian_and_stops():
    """Matches the README's documented failure message — this exact string is
    what a student sees when QVAC is not running."""
    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)), \
         patch.object(chat_service, "_retrieve_and_rank",
                       new=AsyncMock(side_effect=httpx.ConnectError("refused"))):
        chunks = await _drain(chat_service.stream_answer("What is Bitcoin?", COURSE_ID))

    assert len(chunks) == 1
    assert "non è disponibile" in chunks[0]


@pytest.mark.asyncio
async def test_chat_stream_falls_back_to_buffered_generate_when_stream_endpoint_is_down():
    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)), \
         patch.object(chat_service, "_retrieve_and_rank",
                       new=AsyncMock(return_value=([{"label": "d", "text": "t"}], []))), \
         patch.object(chat_service, "_client") as mock_client:
        mock_client.stream = _FakeStreamContext(connect_error=httpx.ConnectError("stream down"))
        mock_client.post = AsyncMock(
            return_value=_qvac_json_response({"answer": "buffered chat answer"})
        )
        chunks = await _drain(chat_service.stream_answer("What is Bitcoin?", COURSE_ID))

    assert chunks[0] == "buffered chat answer"


@pytest.mark.asyncio
async def test_chat_stream_treats_an_error_token_as_a_stream_failure():
    """QVAC returns [ERROR] ... as a regular SSE token rather than an HTTP
    error when the LLM is busy — this must be recognised and trigger fallback,
    not be shown to the student as if it were the answer."""
    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)), \
         patch.object(chat_service, "_retrieve_and_rank",
                       new=AsyncMock(return_value=([{"label": "d", "text": "t"}], []))), \
         patch.object(chat_service, "_client") as mock_client:
        mock_client.stream = _FakeStreamContext(
            lines=[_sse("partial "), _sse("[ERROR] model busy"), "data: [DONE]"]
        )
        mock_client.post = AsyncMock(
            return_value=_qvac_json_response({"answer": "buffered after error token"})
        )
        chunks = await _drain(chat_service.stream_answer("What is Bitcoin?", COURSE_ID))

    # The partial pre-error token is not yielded to the client — a half answer
    # followed by a full fallback answer would be confusing.
    assert "buffered after error token" in chunks


@pytest.mark.asyncio
async def test_chat_stream_falls_back_to_a_raw_source_snippet_when_everything_fails():
    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached"), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)), \
         patch.object(chat_service, "_retrieve_and_rank", new=AsyncMock(
             return_value=([{"label": "d", "text": "raw retrieved passage"}], []))), \
         patch.object(chat_service, "_client") as mock_client:
        mock_client.stream = _FakeStreamContext(connect_error=httpx.ConnectError("down"))
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("generate also down"))
        chunks = await _drain(chat_service.stream_answer("What is Bitcoin?", COURSE_ID))

    assert "raw retrieved passage" in chunks[0]
    assert "non disponibile" in chunks[0]
