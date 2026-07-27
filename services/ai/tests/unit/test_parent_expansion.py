"""Parent expansion — swap child chunk text for richer parent context.

Retrieval matches on short child chunks for precision; generation wants the
surrounding parent text. Citation anchors must stay at child precision so a
citation still points at the right page.

The database lookup is patched throughout: this covers the selection and
substitution logic, not persistence.
"""
from unittest.mock import patch

import pytest

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk
from app.services import parent_expansion


def _chunk(chunk_id: str, text: str, page: int = 1) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=text,
        score=0.9,
        anchor=CitationAnchor(
            doc_id="doc-1",
            doc_name="lecture.pdf",
            section="Consensus",
            page=page,
            slide=None,
            chunk_id=chunk_id,
            chunk_type="paragraph",
        ),
    )


# ---------------------------------------------------------------------------
# Parent id derivation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "child_id,expected",
    [
        ("doc123_p0001_c0002", "doc123_p0001"),
        ("abc_p0010_c0000", "abc_p0010"),
        # QVAC-assigned ids do not follow the pipeline convention.
        ("qvac_docabc_3", None),
        ("no-suffix", None),
        # Suffix must be exactly four digits.
        ("doc_p0001_c12", None),
    ],
)
def test_parent_id_derivation(child_id: str, expected):
    assert parent_expansion._parent_id_from_child(child_id) == expected


# ---------------------------------------------------------------------------
# Expansion behaviour
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty():
    assert parent_expansion.expand_to_parents([]) == []


def test_chunks_without_derivable_parents_are_returned_unchanged():
    """QVAC chunks have no parent convention and must pass through untouched."""
    chunks = [_chunk("qvac_doc_1", "child text")]
    result = parent_expansion.expand_to_parents(chunks)
    assert result == chunks


def test_child_text_is_replaced_by_parent_text():
    chunks = [_chunk("doc1_p0001_c0001", "short child snippet")]

    with patch.object(
        parent_expansion, "_fetch_parent_texts",
        return_value={"doc1_p0001": "the full parent paragraph with context"},
    ):
        result = parent_expansion.expand_to_parents(chunks)

    assert result[0].text == "the full parent paragraph with context"


def test_citation_anchor_stays_at_child_precision():
    """The whole point of keeping anchors: the citation must still point at the
    child's page, not the parent's span."""
    chunks = [_chunk("doc1_p0001_c0001", "child", page=7)]

    with patch.object(
        parent_expansion, "_fetch_parent_texts",
        return_value={"doc1_p0001": "parent text"},
    ):
        result = parent_expansion.expand_to_parents(chunks)

    assert result[0].anchor.page == 7
    assert result[0].anchor.chunk_id == "doc1_p0001_c0001"


def test_only_the_first_sibling_receives_the_parent_text():
    """Two children of the same parent would otherwise inject the same parent
    paragraph twice, wasting the context budget."""
    chunks = [
        _chunk("doc1_p0001_c0001", "first child"),
        _chunk("doc1_p0001_c0002", "second child"),
    ]

    with patch.object(
        parent_expansion, "_fetch_parent_texts",
        return_value={"doc1_p0001": "shared parent text"},
    ):
        result = parent_expansion.expand_to_parents(chunks)

    assert result[0].text == "shared parent text"
    assert result[1].text == "second child", (
        "The second sibling must keep its child text to avoid duplicating the "
        "parent paragraph in the LLM context."
    )


def test_children_of_different_parents_are_both_expanded():
    chunks = [
        _chunk("doc1_p0001_c0001", "child a"),
        _chunk("doc1_p0002_c0001", "child b"),
    ]

    with patch.object(
        parent_expansion, "_fetch_parent_texts",
        return_value={"doc1_p0001": "parent one", "doc1_p0002": "parent two"},
    ):
        result = parent_expansion.expand_to_parents(chunks)

    assert result[0].text == "parent one"
    assert result[1].text == "parent two"


def test_missing_parent_degrades_to_child_text():
    """Expansion is best-effort: a parent row that was never written must not
    lose the passage entirely."""
    chunks = [_chunk("doc1_p0001_c0001", "child text survives")]

    with patch.object(parent_expansion, "_fetch_parent_texts", return_value={}):
        result = parent_expansion.expand_to_parents(chunks)

    assert result[0].text == "child text survives"


def test_database_failure_degrades_to_child_text():
    """A database error during expansion must not fail the study request.

    Patches the database boundary rather than the helper, so this exercises the
    real error handling inside _fetch_parent_texts.
    """
    chunks = [_chunk("doc1_p0001_c0001", "child text survives the outage")]

    with patch(
        "app.db.session.get_db_context", side_effect=RuntimeError("connection refused")
    ):
        result = parent_expansion.expand_to_parents(chunks)

    assert result[0].text == "child text survives the outage"


def test_fetch_parent_texts_returns_empty_mapping_on_database_error():
    with patch(
        "app.db.session.get_db_context", side_effect=RuntimeError("connection refused")
    ):
        assert parent_expansion._fetch_parent_texts(["doc1_p0001"]) == {}


def test_order_is_preserved():
    chunks = [
        _chunk("doc1_p0001_c0001", "a"),
        _chunk("qvac_x_1", "b"),
        _chunk("doc1_p0002_c0001", "c"),
    ]

    with patch.object(
        parent_expansion, "_fetch_parent_texts",
        return_value={"doc1_p0001": "A", "doc1_p0002": "C"},
    ):
        result = parent_expansion.expand_to_parents(chunks)

    assert [c.anchor.chunk_id for c in result] == [
        "doc1_p0001_c0001", "qvac_x_1", "doc1_p0002_c0001",
    ]
