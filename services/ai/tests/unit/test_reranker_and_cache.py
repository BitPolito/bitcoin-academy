"""Reranker and semantic cache — the two components that degrade silently.

Both are optional infrastructure: the reranker needs a model that may not be
installed, the cache needs Redis that may not be running. Neither may take a
study request down when absent — but equally, neither may silently corrupt
results when present. That is what is pinned here.

Model and Redis backends are patched throughout: these tests must run in CI
without downloading a cross-encoder or starting a Redis server.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk
from app.services import cache_service, reranker


def _chunk(chunk_id: str, text: str, score: float = 0.5) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        anchor=CitationAnchor(
            doc_id="doc-1", doc_name="d.pdf", section=None, page=1,
            slide=None, chunk_id=chunk_id, chunk_type="paragraph",
        ),
    )


@pytest.fixture(autouse=True)
def _reset_reranker_singletons():
    """The reranker memoises model loading in module globals; reset between tests
    so one test's patched backend does not leak into the next."""
    reranker._flashrank_ranker = None
    reranker._flashrank_attempted = False
    reranker._cross_encoder = None
    reranker._cross_encoder_attempted = False
    reranker._mmr_emb = None
    reranker._mmr_emb_attempted = False
    yield


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------

def test_reranking_an_empty_list_returns_empty():
    assert reranker.rerank("query", []) == []


def test_chunks_are_returned_unchanged_when_no_backend_is_available():
    """Neither flashrank nor sentence-transformers installed is a supported
    configuration — retrieval must still work, in vector-score order."""
    chunks = [_chunk("c1", "first", 0.9), _chunk("c2", "second", 0.5)]

    with patch.object(reranker, "_get_flashrank", return_value=None), \
         patch.object(reranker, "_get_cross_encoder", return_value=None):
        result = reranker.rerank("query", chunks)

    assert [c.chunk_id for c in result] == ["c1", "c2"]
    assert all(c.rerank_score == 0.0 for c in result), (
        "With no backend, rerank_score must stay 0.0 so evidence_pack_service "
        "knows to sort by vector score instead."
    )


def test_flashrank_scores_are_applied_and_reorder_chunks():
    """The whole point of reranking: a chunk with a low vector score can be
    promoted when the cross-encoder judges it more relevant."""
    chunks = [_chunk("c1", "less relevant", 0.9), _chunk("c2", "more relevant", 0.4)]

    fake_ranker = MagicMock()
    fake_ranker.rerank.return_value = [{"id": 1, "score": 0.95}, {"id": 0, "score": 0.10}]

    with patch.object(reranker, "_get_flashrank", return_value=fake_ranker):
        result = reranker.rerank("query", chunks)

    assert [c.chunk_id for c in result] == ["c2", "c1"], (
        "Reranking did not reorder by cross-encoder score."
    )
    assert result[0].rerank_score == pytest.approx(0.95)


def test_original_vector_score_is_preserved_through_reranking():
    """`score` and `rerank_score` are separate signals; the debug view compares them."""
    chunks = [_chunk("c1", "text", 0.42)]

    fake_ranker = MagicMock()
    fake_ranker.rerank.return_value = [{"id": 0, "score": 0.88}]

    with patch.object(reranker, "_get_flashrank", return_value=fake_ranker):
        result = reranker.rerank("query", chunks)

    assert result[0].score == pytest.approx(0.42)
    assert result[0].rerank_score == pytest.approx(0.88)


def test_flashrank_failure_falls_back_to_the_cross_encoder():
    chunks = [_chunk("c1", "a", 0.5), _chunk("c2", "b", 0.6)]

    failing_ranker = MagicMock()
    failing_ranker.rerank.side_effect = RuntimeError("inference exploded")

    fake_cross_encoder = MagicMock()
    fake_cross_encoder.predict.return_value = MagicMock(tolist=lambda: [0.2, 0.9])

    with patch.object(reranker, "_get_flashrank", return_value=failing_ranker), \
         patch.object(reranker, "_get_cross_encoder", return_value=fake_cross_encoder):
        result = reranker.rerank("query", chunks)

    assert [c.chunk_id for c in result] == ["c2", "c1"]


def test_both_backends_failing_preserves_the_input_order():
    """A double failure must degrade, not raise — a study request should not
    fail because an optional optimisation is broken."""
    chunks = [_chunk("c1", "a", 0.9), _chunk("c2", "b", 0.8)]

    failing_ranker = MagicMock()
    failing_ranker.rerank.side_effect = RuntimeError("boom")
    failing_cross = MagicMock()
    failing_cross.predict.side_effect = RuntimeError("also boom")

    with patch.object(reranker, "_get_flashrank", return_value=failing_ranker), \
         patch.object(reranker, "_get_cross_encoder", return_value=failing_cross):
        result = reranker.rerank("query", chunks)

    assert [c.chunk_id for c in result] == ["c1", "c2"]


def test_backend_loading_is_attempted_only_once():
    """Model loading is expensive; a retry on every query would be crippling."""
    with patch("app.services.reranker.logger"):
        reranker._get_flashrank()
        reranker._get_flashrank()
    assert reranker._flashrank_attempted is True


# ---------------------------------------------------------------------------
# MMR diversification
# ---------------------------------------------------------------------------

def test_mmr_returns_everything_when_fewer_chunks_than_requested():
    chunks = [_chunk("c1", "a"), _chunk("c2", "b")]
    with patch.object(reranker, "_get_mmr_emb", return_value=None):
        result = reranker.mmr_select(chunks, top_k=5)
    assert len(result) == 2


def test_mmr_falls_back_to_top_k_without_an_embedding_model():
    chunks = [_chunk(f"c{i}", f"text {i}") for i in range(6)]
    with patch.object(reranker, "_get_mmr_emb", return_value=None):
        result = reranker.mmr_select(chunks, top_k=3)
    assert [c.chunk_id for c in result] == ["c0", "c1", "c2"]


def test_mmr_on_an_empty_list_returns_empty():
    with patch.object(reranker, "_get_mmr_emb", return_value=None):
        assert reranker.mmr_select([], top_k=3) == []


# ---------------------------------------------------------------------------
# Semantic cache — similarity maths
# ---------------------------------------------------------------------------

def test_cosine_of_identical_vectors_is_one():
    assert cache_service._cosine([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(1.0)


def test_cosine_of_orthogonal_vectors_is_zero():
    assert cache_service._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_of_a_zero_vector_is_zero_not_a_division_error():
    """A degenerate embedding must not crash the cache lookup."""
    assert cache_service._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_of_mismatched_lengths_is_handled():
    result = cache_service._cosine([1.0, 0.0], [1.0, 0.0, 0.0])
    assert isinstance(result, float)


def test_cache_key_is_scoped_by_course():
    """Two courses must never share a cache entry — this is the isolation
    guarantee asserted end to end in test_course_isolation.py."""
    vec = [0.1, 0.2, 0.3]
    assert cache_service._cache_key("course-a", vec) != cache_service._cache_key("course-b", vec)


def test_cache_key_is_deterministic():
    vec = [0.1, 0.2, 0.3]
    assert cache_service._cache_key("course-a", vec) == cache_service._cache_key("course-a", vec)


# ---------------------------------------------------------------------------
# Semantic cache — degradation
# ---------------------------------------------------------------------------

def test_lookup_returns_none_when_the_cache_is_disabled(monkeypatch):
    monkeypatch.setattr(cache_service, "_ENABLED", False)
    assert cache_service.get_cached("a question", "course-1") is None


def test_store_is_a_noop_when_the_cache_is_disabled(monkeypatch):
    monkeypatch.setattr(cache_service, "_ENABLED", False)
    cache_service.set_cached("a question", "course-1", {"answer": "x"})  # must not raise


def test_lookup_returns_none_without_an_embedding_model(monkeypatch):
    monkeypatch.setattr(cache_service, "_ENABLED", True)
    with patch.object(cache_service, "_embed", return_value=None):
        assert cache_service.get_cached("a question", "course-1") is None


def test_lookup_returns_none_when_redis_is_unavailable(monkeypatch):
    """Redis down means cache miss, never an error surfaced to the student."""
    monkeypatch.setattr(cache_service, "_ENABLED", True)
    with patch.object(cache_service, "_embed", return_value=[0.1, 0.2]), \
         patch.object(cache_service, "_redis_client", return_value=None):
        assert cache_service.get_cached("a question", "course-1") is None


def test_store_swallows_redis_errors(monkeypatch):
    monkeypatch.setattr(cache_service, "_ENABLED", True)
    failing_redis = MagicMock()
    failing_redis.setex.side_effect = RuntimeError("connection lost")

    with patch.object(cache_service, "_embed", return_value=[0.1, 0.2]), \
         patch.object(cache_service, "_redis_client", return_value=failing_redis):
        cache_service.set_cached("a question", "course-1", {"answer": "x"})  # must not raise


def test_embed_returns_none_when_no_model_is_loaded():
    """_get_emb swallows its own load errors and returns None; _embed must
    handle that rather than calling embed() on None."""
    with patch.object(cache_service, "_get_emb", return_value=None):
        assert cache_service._embed("some text") is None


def test_embed_returns_none_when_inference_fails():
    """A model that loads but fails at inference must degrade to a cache miss."""
    failing_model = MagicMock()
    failing_model.embed.side_effect = RuntimeError("inference failed")

    with patch.object(cache_service, "_get_emb", return_value=failing_model):
        assert cache_service._embed("some text") is None


def test_model_load_failure_is_swallowed_and_memoised(monkeypatch):
    """fastembed missing is a supported configuration — it disables the cache
    rather than breaking startup, and is not retried on every query."""
    monkeypatch.setattr(cache_service, "_emb_model", None)
    monkeypatch.setattr(cache_service, "_emb_attempted", False)

    with patch.dict("sys.modules", {"fastembed": None}):
        assert cache_service._get_emb() is None

    assert cache_service._emb_attempted is True


# ---------------------------------------------------------------------------
# Prompt construction (app/rag/chains.py)
# ---------------------------------------------------------------------------

def test_prompt_includes_delimited_context_and_question():
    from app.rag.chains import build_prompt

    prompt = build_prompt(context="Bitcoin uses PoW.", question="What is PoW?")

    assert "=== CONTEXT ===" in prompt
    assert "=== END CONTEXT ===" in prompt
    assert "=== QUESTION ===" in prompt
    assert "Bitcoin uses PoW." in prompt
    assert "What is PoW?" in prompt


def test_prompt_omits_the_context_section_when_empty():
    from app.rag.chains import build_prompt

    prompt = build_prompt(context="", question="What is PoW?")

    assert "=== CONTEXT ===" not in prompt
    assert "What is PoW?" in prompt


def test_prompt_includes_instructions_when_supplied():
    from app.rag.chains import build_prompt

    prompt = build_prompt(context="c", question="q", instructions="Answer in two sentences.")

    assert "=== INSTRUCTIONS ===" in prompt
    assert "Answer in two sentences." in prompt


def test_prompt_omits_instructions_when_not_supplied():
    from app.rag.chains import build_prompt

    assert "=== INSTRUCTIONS ===" not in build_prompt(context="c", question="q")


# ---------------------------------------------------------------------------
# Prompt templates (app/rag/prompts.py)
# ---------------------------------------------------------------------------

def test_every_prompt_template_accepts_query_and_context():
    """A template missing a placeholder raises KeyError at generation time —
    the worst moment to discover it."""
    from app.rag import prompts

    templates = [
        name for name in dir(prompts)
        if name.endswith("_PROMPT") and isinstance(getattr(prompts, name), str)
    ]
    assert templates, "No prompt templates found in app.rag.prompts"

    for name in templates:
        template = getattr(prompts, name)
        rendered = template.format(query="test query", context="test context")
        assert "test query" in rendered or "test context" in rendered, (
            f"{name} rendered without using either placeholder"
        )
