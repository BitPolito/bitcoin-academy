"""Unit tests for app.services.evidence_pack_service.

Covers _deduplicate(), _apply_boost(), and build_from_chunks().
Reranker and parent_expansion are mocked; no external services needed.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk
from app.services.evidence_pack_service import (
    _apply_boost,
    _deduplicate,
    build_from_chunks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(chunk_id: str, text: str = "Some text.", score: float = 0.8,
           chunk_type: str = "paragraph") -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        anchor=CitationAnchor(
            doc_id="DOC1",
            doc_name="doc.pdf",
            section=None,
            page=1,
            slide=None,
            chunk_id=chunk_id,
            chunk_type=chunk_type,
        ),
    )


# ---------------------------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_deduplicate_removes_duplicate_chunk_ids():
    chunks = [_chunk("c1"), _chunk("c1"), _chunk("c2")]
    result = _deduplicate(chunks)
    ids = [c.chunk_id for c in result]
    assert ids == ["c1", "c2"]


@pytest.mark.unit
def test_deduplicate_preserves_order():
    chunks = [_chunk("c3"), _chunk("c1"), _chunk("c2")]
    result = _deduplicate(chunks)
    assert [c.chunk_id for c in result] == ["c3", "c1", "c2"]


@pytest.mark.unit
def test_deduplicate_empty_input():
    assert _deduplicate([]) == []


@pytest.mark.unit
def test_deduplicate_no_duplicates_returns_same():
    chunks = [_chunk("c1"), _chunk("c2"), _chunk("c3")]
    result = _deduplicate(chunks)
    assert [c.chunk_id for c in result] == ["c1", "c2", "c3"]


# ---------------------------------------------------------------------------
# _apply_boost
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_apply_boost_boosts_past_exam_for_quiz():
    exam_chunk = _chunk("c1", score=0.5, chunk_type="past_exam")
    other_chunk = _chunk("c2", score=0.5, chunk_type="paragraph")
    result = _apply_boost([exam_chunk, other_chunk], "quiz")
    assert result[0].score > 0.5   # boosted
    assert result[1].score == 0.5  # unchanged


@pytest.mark.unit
def test_apply_boost_boosts_past_exam_for_oral():
    exam_chunk = _chunk("c1", score=0.5, chunk_type="past_exam")
    result = _apply_boost([exam_chunk], "oral")
    assert result[0].score == pytest.approx(0.6, abs=0.001)


@pytest.mark.unit
def test_apply_boost_caps_score_at_one():
    exam_chunk = _chunk("c1", score=0.95, chunk_type="past_exam")
    result = _apply_boost([exam_chunk], "quiz")
    assert result[0].score <= 1.0


@pytest.mark.unit
def test_apply_boost_ignores_non_quiz_oral_actions():
    exam_chunk = _chunk("c1", score=0.5, chunk_type="past_exam")
    for action in ("explain", "summarize", "retrieve", "open_questions", "derive", "compare"):
        result = _apply_boost([exam_chunk], action)
        assert result[0].score == 0.5, f"score changed for action={action}"


@pytest.mark.unit
def test_apply_boost_empty_input():
    assert _apply_boost([], "quiz") == []


# ---------------------------------------------------------------------------
# build_from_chunks
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_build_from_chunks_empty_input_returns_empty_pack():
    with patch("app.services.reranker.rerank", return_value=[]), \
         patch("app.services.parent_expansion.expand_to_parents", return_value=[]):
        pack = build_from_chunks("Q", "explain", [])

    assert pack.chunks == []
    assert pack.deduped_passages == []
    assert pack.total_candidates == 0


@pytest.mark.unit
def test_build_from_chunks_returns_pack_with_correct_query():
    chunk = _chunk("c1", text="Some evidence.")
    with patch("app.services.reranker.rerank", return_value=[chunk]), \
         patch("app.services.parent_expansion.expand_to_parents", return_value=[chunk]):
        pack = build_from_chunks("My query", "explain", [chunk])

    assert pack.query == "My query"
    assert pack.action == "explain"


@pytest.mark.unit
def test_build_from_chunks_deduplicates_before_rerank():
    dup = _chunk("c1")
    with patch("app.services.evidence_pack_service._deduplicate", wraps=_deduplicate) as mock_dedup, \
         patch("app.services.reranker.rerank", return_value=[dup]), \
         patch("app.services.parent_expansion.expand_to_parents", return_value=[dup]):
        build_from_chunks("Q", "explain", [dup, dup])

    mock_dedup.assert_called_once()
    _, call_args_list = mock_dedup.call_args
    # dedup was called with 2 chunks (the duplicates)
    passed = mock_dedup.call_args[0][0]
    assert len(passed) == 2


@pytest.mark.unit
def test_build_from_chunks_token_truncation_stops_at_budget():
    # each chunk ~200 chars → ~50 tokens; set max_tokens low to force truncation
    chunks = [_chunk(f"c{i}", text="x" * 200, score=float(1.0 - i * 0.1)) for i in range(5)]
    with patch("app.services.reranker.rerank", return_value=chunks), \
         patch("app.services.parent_expansion.expand_to_parents", side_effect=lambda x: x):
        pack = build_from_chunks("Q", "explain", chunks, max_tokens=60)

    # 60 tokens / 50 tokens-per-chunk = at most 1 chunk fits before budget is exceeded
    assert len(pack.chunks) <= 2
    assert pack.truncated is True


@pytest.mark.unit
def test_build_from_chunks_sources_unique_doc_names():
    c1 = _chunk("c1", text="A")
    c2 = _chunk("c2", text="B")
    c1.anchor.doc_name = "doc_a.pdf"  # type: ignore[attr-defined]
    c2.anchor.doc_name = "doc_a.pdf"
    with patch("app.services.reranker.rerank", return_value=[c1, c2]), \
         patch("app.services.parent_expansion.expand_to_parents", side_effect=lambda x: x):
        pack = build_from_chunks("Q", "explain", [c1, c2])

    assert pack.sources == ["doc_a.pdf"]


@pytest.mark.unit
def test_build_from_chunks_total_candidates_reflects_input():
    chunks = [_chunk(f"c{i}") for i in range(7)]
    with patch("app.services.reranker.rerank", return_value=chunks[:3]), \
         patch("app.services.parent_expansion.expand_to_parents", side_effect=lambda x: x):
        pack = build_from_chunks("Q", "explain", chunks)

    assert pack.total_candidates == 7
