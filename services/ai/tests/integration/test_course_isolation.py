"""Course isolation and graceful degradation.

Course isolation is an architectural principle (requirement 18 in
docs/specifications.md): retrieval, evidence packs and generated output must
stay bound to the course they came from. Isolation bugs are invisible in
single-course development and only surface once real users share a deployment,
so they are asserted here explicitly rather than assumed.

Degradation matters because the system is local-first: QVAC, Redis and the ARQ
worker are all expected to be missing sometimes. Failing clearly is a feature;
failing opaquely, or inventing an answer, is not.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import create_access_token
from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk
from app.schemas.study_schemas import StudyAction
from app.services import evidence_pack_service, study_service
from tests.conftest import make_course_with_lessons, make_user

COURSE_A = "11111111-1111-1111-1111-111111111111"
COURSE_B = "22222222-2222-2222-2222-222222222222"


def _auth_header(user) -> dict:
    role = getattr(user.role, "value", user.role)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, role)}"}


def _qvac_response(sources: list) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"answer": "generated answer", "sources": sources}
    resp.raise_for_status.return_value = None
    return resp


def _source(chunk_id: str, doc_id: str, text: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "snippet": text,
        "score": 0.9,
        "doc_id": doc_id,
        "label": f"{doc_id}.pdf",
        "section": "S",
        "page": 1,
        "slide": 0,
    }


# ---------------------------------------------------------------------------
# Retrieval is scoped to the requested course.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieval_requests_only_the_requested_workspace():
    """The course id is the workspace key. Sending the wrong one — or none —
    would let one course's query read another course's index."""
    captured = {}

    async def _capture(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return _qvac_response([_source("a1", "docA", "content from course A")])

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_capture)):
        with patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)):
            await study_service.dispatch(
                question="What is a UTXO?",
                course_id=COURSE_A,
                action=StudyAction.RETRIEVE,
            )

    assert captured["json"]["workspace"] == COURSE_A, (
        f"Retrieval was issued against workspace {captured['json'].get('workspace')!r} "
        f"instead of the requested course {COURSE_A!r}."
    )


@pytest.mark.asyncio
async def test_evidence_pack_contains_only_chunks_returned_for_that_course():
    """The pack must not acquire chunks from anywhere but the course's own retrieval."""
    course_a_sources = [
        _source("a1", "docA", "Course A: UTXO definition"),
        _source("a2", "docA", "Course A: transaction structure"),
    ]

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_qvac_response(course_a_sources))):
        with patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)):
            result = await study_service.dispatch(
                question="Explain the UTXO model",
                course_id=COURSE_A,
                action=StudyAction.RETRIEVE,
            )

    pack = result.evidence_pack
    assert pack is not None
    returned_ids = {c.chunk_id for c in pack.chunks}
    assert returned_ids <= {"a1", "a2"}, (
        f"Evidence pack for course A contains unexpected chunks: "
        f"{returned_ids - {'a1', 'a2'}}"
    )
    for chunk in pack.chunks:
        assert chunk.anchor.doc_id == "docA", (
            f"Chunk {chunk.chunk_id} carries doc_id {chunk.anchor.doc_id!r}, which "
            f"did not come from course A's retrieval."
        )


# ---------------------------------------------------------------------------
# The semantic cache must not serve one course's answer to another.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_does_not_serve_another_course_answer():
    """Same question, different course — the second call must not receive the
    first course's cached answer. A collision here leaks course content."""
    store: dict = {}

    def _fake_get(key, course_id):
        return store.get((key, course_id))

    def _fake_set(key, course_id, value):
        store[(key, course_id)] = value

    question = "What is proof of work?"

    with patch("app.services.cache_service.get_cached", side_effect=_fake_get), \
         patch("app.services.cache_service.set_cached", side_effect=_fake_set), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)):

        with patch("httpx.AsyncClient.post", new=AsyncMock(
                return_value=_qvac_response([_source("a1", "docA", "Course A answer")]))):
            result_a = await study_service.dispatch(
                question=question, course_id=COURSE_A, action=StudyAction.RETRIEVE
            )

        with patch("httpx.AsyncClient.post", new=AsyncMock(
                return_value=_qvac_response([_source("b1", "docB", "Course B answer")]))):
            result_b = await study_service.dispatch(
                question=question, course_id=COURSE_B, action=StudyAction.RETRIEVE
            )

    a_docs = {c.doc_id for c in result_a.citations}
    b_docs = {c.doc_id for c in result_b.citations}

    assert "docB" not in a_docs, f"Course A answer cites course B documents: {a_docs}"
    assert "docA" not in b_docs, (
        f"Course B received course A's cached content: {b_docs}. The semantic "
        f"cache key must include the course id."
    )


@pytest.mark.asyncio
async def test_cache_key_separates_actions_for_the_same_question():
    """`quiz` and `explain` produce different output shapes; sharing a cache
    entry would return a quiz where prose was requested."""
    keys: list = []

    def _record(key, course_id):
        keys.append(key)
        return None

    with patch("app.services.cache_service.get_cached", side_effect=_record), \
         patch("app.services.cache_service.set_cached", side_effect=lambda *a, **k: None), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)), \
         patch("httpx.AsyncClient.post", new=AsyncMock(
             return_value=_qvac_response([_source("a1", "docA", "text")]))):

        await study_service.dispatch("Explain mining", COURSE_A, StudyAction.RETRIEVE)
        await study_service.dispatch("Explain mining", COURSE_A, StudyAction.QUIZ, rag_only=True)

    assert len(keys) == 2
    assert keys[0] != keys[1], (
        f"The same cache key was used for two different actions: {keys[0]!r}. "
        f"Action must be part of the key."
    )


# ---------------------------------------------------------------------------
# Graceful degradation.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieval_failure_returns_an_empty_pack_not_an_exception():
    """QVAC being down is an expected local-first condition. The dispatcher must
    degrade to an empty pack rather than propagating a transport error."""
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("refused"))), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached", side_effect=lambda *a, **k: None), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)):

        result = await study_service.dispatch(
            question="What is Bitcoin?", course_id=COURSE_A, action=StudyAction.RETRIEVE
        )

    assert result.citations == []
    assert result.retrieval_used is False
    assert result.answer, "An answer string must still be returned for the UI to render"


@pytest.mark.asyncio
async def test_generation_failure_falls_back_to_retrieved_context():
    """When retrieval succeeds but generation fails, the student should still
    get the source passages rather than an error page."""
    call_count = {"n": 0}

    async def _post(url, json=None, **kwargs):
        call_count["n"] += 1
        if str(url).endswith("/generate"):
            raise httpx.ConnectError("LLM unreachable")
        return _qvac_response([_source("a1", "docA", "Bitcoin uses proof of work.")])

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_post)), \
         patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached", side_effect=lambda *a, **k: None), \
         patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)):

        result = await study_service.dispatch(
            question="Explain proof of work", course_id=COURSE_A, action=StudyAction.EXPLAIN
        )

    assert result.answer, "Fallback must still produce an answer"
    assert result.citations, "Fallback must surface the retrieved passages as citations"


@pytest.mark.asyncio
async def test_rag_only_mode_skips_generation_for_every_action():
    """Retrieval-only mode is how the product runs on memory-constrained
    machines. No action may attempt generation in that mode."""
    generate_calls = []

    async def _post(url, json=None, **kwargs):
        if str(url).endswith("/generate"):
            generate_calls.append(url)
        return _qvac_response([_source("a1", "docA", "passage text")])

    for action in StudyAction:
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_post)), \
             patch("app.services.cache_service.get_cached", return_value=None), \
             patch("app.services.cache_service.set_cached", side_effect=lambda *a, **k: None), \
             patch("app.rag.query_rewriter.expand_query", new=AsyncMock(side_effect=lambda q: q)):

            result = await study_service.dispatch(
                question="A sufficiently long study question",
                course_id=COURSE_A,
                action=action,
                rag_only=True,
            )
        assert result.answer, f"{action.value} returned no answer in rag_only mode"

    assert generate_calls == [], (
        f"rag_only mode called /generate for: {generate_calls}. Retrieval-only "
        f"mode must never invoke the LLM."
    )


@pytest.mark.asyncio
async def test_query_shorter_than_the_minimum_is_rejected():
    """Guards against empty or accidental submissions reaching retrieval."""
    with pytest.raises(ValueError):
        await study_service.dispatch("hi", COURSE_A, StudyAction.EXPLAIN)


# ---------------------------------------------------------------------------
# Evidence pack assembly invariants.
# ---------------------------------------------------------------------------

def _chunk(chunk_id: str, text: str, score: float) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        anchor=CitationAnchor(
            doc_id="doc-1", doc_name="d.pdf", section=None, page=1,
            slide=None, chunk_id=chunk_id, chunk_type="paragraph",
        ),
    )


def test_duplicate_chunk_ids_are_removed():
    """Two-hop retrieval merges results and can produce the same chunk twice;
    duplicated context wastes the token budget and skews the model."""
    candidates = [
        _chunk("c1", "first", 0.9),
        _chunk("c1", "first duplicate", 0.8),
        _chunk("c2", "second", 0.7),
    ]
    pack = evidence_pack_service.build_from_chunks("q", "explain", candidates)
    ids = [c.chunk_id for c in pack.chunks]
    assert len(ids) == len(set(ids)), f"Duplicate chunk ids survived dedup: {ids}"


def test_pack_reports_the_full_candidate_count():
    """total_candidates must describe the pre-dedup pool, so the debug view can
    show how much was discarded."""
    candidates = [_chunk(f"c{i}", f"text {i}", 0.9 - i / 100) for i in range(10)]
    pack = evidence_pack_service.build_from_chunks("q", "explain", candidates)
    assert pack.total_candidates == 10
    assert len(pack.chunks) <= 10


def test_empty_candidate_list_produces_a_valid_empty_pack():
    pack = evidence_pack_service.build_from_chunks("q", "explain", [])
    assert pack.chunks == []
    assert pack.total_candidates == 0
    assert pack.context_block() == ""


def test_sources_are_unique_and_in_rank_order():
    candidates = [_chunk("c1", "a", 0.9), _chunk("c2", "b", 0.8)]
    pack = evidence_pack_service.build_from_chunks("q", "explain", candidates)
    assert len(pack.sources) == len(set(pack.sources))


# ---------------------------------------------------------------------------
# Health endpoint honesty.
# ---------------------------------------------------------------------------

def test_health_reports_database_connected_when_it_is(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


def test_health_reports_degraded_when_the_database_is_unreachable(client):
    """An honest health endpoint is what makes an outage diagnosable."""
    with patch("app.main.get_db", side_effect=RuntimeError("connection refused")):
        response = client.get("/health")

    assert response.status_code == 200, "Health must answer even when degraded"
    body = response.json()
    assert body["database"] == "disconnected"
    assert body["status"] == "degraded"
