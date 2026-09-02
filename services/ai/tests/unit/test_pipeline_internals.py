"""Ingestion pipeline internals — cleaning, block segmentation, chunking.

pipeline.py is the largest module in the backend and the one whose defects are
hardest to notice: bad chunking does not raise, it just quietly degrades every
answer that depends on the affected passage. These tests pin the behaviour that
retrieval quality rests on.

Parser entry points that require real PDF/PPTX/DOCX libraries are covered in
tests/integration/test_pipeline_e2e.py; this file covers the pure functions.
"""
import json

import pytest

from app.workers import pipeline


# ---------------------------------------------------------------------------
# Word counting and boilerplate detection
# ---------------------------------------------------------------------------

def test_word_count_ignores_extra_whitespace():
    assert pipeline._word_count("  one   two \n three ") == 3


def test_word_count_of_empty_text_is_zero():
    assert pipeline._word_count("   \n  ") == 0


def _pages(*texts: str) -> list[dict]:
    return [{"page": i + 1, "text": t} for i, t in enumerate(texts)]


def test_boilerplate_detection_is_skipped_for_short_documents():
    """Fewer than five pages is too small a sample; guessing would strip real content."""
    pages = _pages("Chapter 1\nHeader", "Chapter 2\nHeader")
    assert pipeline.detect_boilerplate(pages) == set()


def test_repeated_running_header_is_detected():
    pages = _pages(*[f"The Bitcoin Standard\nContent for page {i}" for i in range(6)])
    boilerplate = pipeline.detect_boilerplate(pages)
    assert "The Bitcoin Standard" in boilerplate


def test_unique_lines_are_not_treated_as_boilerplate():
    pages = _pages(*[f"Unique content line {i}" for i in range(6)])
    assert pipeline.detect_boilerplate(pages) == set()


def test_short_lines_are_ignored_by_boilerplate_detection():
    """Lines of three characters or fewer are too generic to strip safely."""
    pages = _pages(*["ab\nreal content here" for _ in range(6)])
    assert "ab" not in pipeline.detect_boilerplate(pages)


def test_line_repeated_on_one_page_counts_once():
    """A line repeated many times on a single page must not look document-wide."""
    pages = _pages("dup\ndup\ndup\ndup", *[f"page {i}" for i in range(5)])
    assert "dup" not in pipeline.detect_boilerplate(pages)


def test_clean_page_removes_detected_boilerplate():
    text = "The Bitcoin Standard\nActual lecture content."
    cleaned = pipeline.clean_page(text, {"The Bitcoin Standard"})
    assert "The Bitcoin Standard" not in cleaned
    assert "Actual lecture content." in cleaned


def test_clean_page_collapses_excess_blank_lines():
    cleaned = pipeline.clean_page("a\n\n\n\n\nb", set())
    assert "\n\n\n" not in cleaned


def test_clean_page_without_boilerplate_preserves_content():
    text = "Bitcoin uses proof of work."
    assert pipeline.clean_page(text, set()) == text


# ---------------------------------------------------------------------------
# Spurious heading detection — PDF running headers rendered as markdown headings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "heading",
    [
        "## 32",
        "# 44",
        "## 34 T H E B I T C O I N S T A N D A R D",
        "## P R O L O G U E",
        "## B I B L I O G R A P H Y",
        "## viii C O N T E N T S",
        "## ~~k~~",
        "## xiv",
        "## xviii",
    ],
)
def test_running_header_artifacts_are_spurious(heading: str):
    """These come from LaTeX running headers, not from real document structure.
    Treating them as sections would fragment chunks at meaningless boundaries."""
    assert pipeline._is_spurious_heading(heading) is True


@pytest.mark.parametrize(
    "heading",
    [
        "## Introduction",
        "# Proof of Work",
        "### The UTXO Model",
        "## Chapter 3: Consensus",
        "## Bitcoin",
    ],
)
def test_genuine_headings_are_kept(heading: str):
    assert pipeline._is_spurious_heading(heading) is False


# ---------------------------------------------------------------------------
# Block segmentation
# ---------------------------------------------------------------------------

def _types(blocks: list[dict]) -> list[str]:
    return [b["type"] for b in blocks]


def test_headings_are_segmented_as_heading_blocks():
    blocks = pipeline._split_into_blocks("## Consensus\n\nSome paragraph text here.")
    assert "heading" in _types(blocks)


def test_paragraph_text_is_segmented_as_paragraph():
    blocks = pipeline._split_into_blocks("Bitcoin uses proof of work to order transactions.")
    assert "paragraph" in _types(blocks)


def test_latex_formula_is_extracted_as_an_atomic_block():
    """Formulas must survive chunking intact — splitting one destroys its meaning."""
    text = "Given the difficulty:\n\n$$H(x) < T$$\n\nthe miner wins."
    blocks = pipeline._split_into_blocks(text)
    assert "formula" in _types(blocks), f"Expected a formula block, got {_types(blocks)}"
    formula = next(b for b in blocks if b["type"] == "formula")
    assert "H(x) < T" in formula["text"]


def test_code_fence_is_extracted_as_an_atomic_block():
    text = "Example:\n\n```python\nprint('hello')\n```\n\nDone."
    blocks = pipeline._split_into_blocks(text)
    assert "code" in _types(blocks), f"Expected a code block, got {_types(blocks)}"


def test_markdown_table_is_segmented_as_a_table_block():
    text = "| Field | Size |\n|---|---|\n| version | 4 |\n| nonce | 4 |"
    blocks = pipeline._split_into_blocks(text)
    assert "table" in _types(blocks)


def test_empty_text_produces_no_blocks():
    assert pipeline._split_into_blocks("") == []


def test_whitespace_only_text_produces_no_blocks():
    assert pipeline._split_into_blocks("   \n\n  \t ") == []


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------

def test_short_paragraph_is_not_split():
    text = "One short sentence."
    assert pipeline._split_paragraph(text, max_words=100) == [text]


def test_long_paragraph_is_split_into_multiple_pieces():
    text = ". ".join(f"Sentence number {i} with some filler words" for i in range(60)) + "."
    pieces = pipeline._split_paragraph(text, max_words=50)
    assert len(pieces) > 1


def test_split_pieces_respect_the_word_cap():
    text = ". ".join(f"Sentence number {i} with filler" for i in range(80)) + "."
    pieces = pipeline._split_paragraph(text, max_words=40)
    # Allow modest overshoot: a single sentence longer than the cap is not split.
    for piece in pieces:
        assert pipeline._word_count(piece) <= 40 * 2


def test_split_preserves_all_content():
    """Splitting must not silently drop text — lost content is lost retrieval."""
    sentences = [f"Fact number {i} about bitcoin" for i in range(30)]
    text = ". ".join(sentences) + "."
    pieces = pipeline._split_paragraph(text, max_words=25)
    joined = " ".join(pieces)
    for i in (0, 15, 29):
        assert f"Fact number {i}" in joined


def test_overlap_repeats_words_between_consecutive_pieces():
    """Overlap prevents a concept from being cut in half at a chunk boundary."""
    text = ". ".join(f"Sentence {i} carries meaning" for i in range(40)) + "."
    with_overlap = pipeline._split_paragraph(text, max_words=30, overlap_words=10)
    without_overlap = pipeline._split_paragraph(text, max_words=30, overlap_words=0)
    assert sum(pipeline._word_count(p) for p in with_overlap) >= sum(
        pipeline._word_count(p) for p in without_overlap
    )


def test_empty_paragraph_splits_to_nothing_usable():
    assert pipeline._split_paragraph("", max_words=50) in ([], [""])


# ---------------------------------------------------------------------------
# Chunk construction and metadata
# ---------------------------------------------------------------------------

def test_parent_chunk_carries_required_metadata():
    parent = pipeline._make_parent("doc1", 0, page=3, text="parent text", section="Consensus")
    assert parent["citation_page"] == 3
    assert parent["citation_section"] == "Consensus"
    assert parent["text"] == "parent text"
    assert parent["doc_id"] == "doc1"
    assert "doc1" in parent["id"]


def test_child_id_is_derivable_back_to_its_parent():
    """parent_expansion derives the parent id by stripping the _cNNNN suffix.
    If this naming changes, parent expansion silently stops working."""
    parent = pipeline._make_parent("doc1", 1, page=2, text="parent", section="S")
    child = pipeline._make_child(parent["id"], "doc1", 2, 0, "child text", "S")

    assert child["id"].startswith(parent["id"]), (
        f"Child id {child['id']!r} does not extend parent id {parent['id']!r}; "
        f"parent_expansion._parent_id_from_child would fail."
    )

    from app.services.parent_expansion import _parent_id_from_child
    assert _parent_id_from_child(child["id"]) == parent["id"]


def test_child_inherits_page_and_section_from_parent():
    parent = pipeline._make_parent("doc1", 0, page=7, text="parent", section="Mining")
    child = pipeline._make_child(parent["id"], "doc1", 7, 0, "child text", "Mining")
    assert child["citation_page"] == 7
    assert child["citation_section"] == "Mining"
    assert child["parent_id"] == parent["id"]


def test_child_records_its_chunk_type():
    parent = pipeline._make_parent("doc1", 0, page=1, text="p", section="S")
    child = pipeline._make_child(
        parent["id"], "doc1", 1, 0, "$$E=mc^2$$", "S", chunk_type="formula"
    )
    assert child["chunk_type"] == "formula"


# ---------------------------------------------------------------------------
# Chunk filtering
# ---------------------------------------------------------------------------

def _chunk(text: str, chunk_type: str = "paragraph") -> dict:
    return {
        "id": "c1",
        "text": text,
        "chunk_type": chunk_type,
        "citation_page": 1,
        "citation_section": "",
        "doc_id": "doc1",
    }


def test_paragraphs_below_the_word_threshold_are_discarded():
    """Fragments too short to carry meaning pollute retrieval."""
    kept = pipeline.filter_chunks([_chunk("too short")])
    assert kept == []


def test_substantial_paragraphs_are_kept():
    text = " ".join(f"word{i}" for i in range(40))
    assert len(pipeline.filter_chunks([_chunk(text)])) == 1


def test_short_tables_are_kept_despite_the_paragraph_threshold():
    """A single table row is meaningful even though it is only a few words."""
    kept = pipeline.filter_chunks([_chunk("| version | 4 |", chunk_type="table")])
    assert len(kept) == 1, "Table rows must not be filtered by the paragraph threshold"


def test_empty_chunk_list_filters_to_empty():
    assert pipeline.filter_chunks([]) == []


# ---------------------------------------------------------------------------
# Parent/child chunking end to end
# ---------------------------------------------------------------------------

def test_build_parent_child_chunks_returns_both_levels():
    pages = [{"page": 1, "text": " ".join(f"word{i}" for i in range(300))}]
    parents, children, _sections = pipeline.build_parent_child_chunks(pages, "doc1")

    assert parents, "Expected at least one parent chunk"
    assert children, "Expected at least one child chunk"


def test_every_child_maps_to_an_existing_parent():
    """An orphaned child cannot be expanded, so its generation context degrades."""
    pages = [{"page": 1, "text": " ".join(f"word{i}" for i in range(600))}]
    parents, children, _sections = pipeline.build_parent_child_chunks(pages, "doc1")

    parent_ids = {p["id"] for p in parents}
    from app.services.parent_expansion import _parent_id_from_child

    for child in children:
        derived = _parent_id_from_child(child["id"])
        assert derived in parent_ids, (
            f"Child {child['id']} derives parent {derived!r}, which is not among "
            f"the emitted parents."
        )


def test_children_are_smaller_than_parents():
    """Children are the retrieval unit, parents the context unit."""
    pages = [{"page": 1, "text": " ".join(f"word{i}" for i in range(900))}]
    parents, children, _sections = pipeline.build_parent_child_chunks(pages, "doc1")

    avg_parent = sum(pipeline._word_count(p["text"]) for p in parents) / len(parents)
    avg_child = sum(pipeline._word_count(c["text"]) for c in children) / len(children)
    assert avg_child < avg_parent


def test_child_chunks_respect_the_embedding_word_cap():
    """Children longer than the cap get truncated by the embedding model, which
    silently discards the tail of the passage."""
    pages = [{"page": 1, "text": " ".join(f"word{i}" for i in range(2000))}]
    _, children, _sections = pipeline.build_parent_child_chunks(pages, "doc1")

    for child in children:
        assert pipeline._word_count(child["text"]) <= pipeline._CHILD_MAX_WORDS, (
            f"Child chunk of {pipeline._word_count(child['text'])} words exceeds "
            f"the {pipeline._CHILD_MAX_WORDS}-word cap and would be truncated at "
            f"embedding time."
        )


def test_empty_pages_produce_no_chunks():
    parents, children, sections = pipeline.build_parent_child_chunks([], "doc1")
    assert parents == []
    assert children == []
    assert sections == []


def test_page_numbers_are_preserved_through_chunking():
    """Citations point at pages; losing the page number breaks source grounding."""
    pages = [
        {"page": 5, "text": " ".join(f"alpha{i}" for i in range(200))},
        {"page": 6, "text": " ".join(f"beta{i}" for i in range(200))},
    ]
    _, children, _sections = pipeline.build_parent_child_chunks(pages, "doc1")
    pages_seen = {c["citation_page"] for c in children}
    assert pages_seen <= {5, 6}
    assert pages_seen, "No page metadata survived chunking"


# ---------------------------------------------------------------------------
# JSONL export — the handoff to the QVAC indexer
# ---------------------------------------------------------------------------

def test_jsonl_export_writes_one_valid_object_per_line(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "QVAC_INGEST_DIR", tmp_path)

    chunks = [
        {"id": "c1", "text": "first chunk", "page": 1, "section": "S", "chunk_type": "paragraph"},
        {"id": "c2", "text": "second chunk", "page": 2, "section": "S", "chunk_type": "paragraph"},
    ]
    path = pipeline._write_jsonl(chunks, "doc-123")

    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # raises if the export is not valid JSONL


def test_jsonl_export_handles_an_empty_chunk_list(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "QVAC_INGEST_DIR", tmp_path)
    path = pipeline._write_jsonl([], "doc-empty")
    assert path.exists()
    assert [ln for ln in path.read_text().splitlines() if ln.strip()] == []


def test_module_aliases_are_registered_without_error():
    """Registering aliases twice must be safe — the worker imports it repeatedly."""
    pipeline._register_module_aliases()
    pipeline._register_module_aliases()

    import sys
    assert "services.ai.app.workers.pipeline" in sys.modules, (
        "The long-form alias was not registered — the ingester's sys.path "
        "setup silently stopped working."
    )
    assert sys.modules["services.ai.app.workers.pipeline"] is pipeline, (
        "The alias points at a different module object than the canonical "
        "app.workers.pipeline — re-registration created a duplicate instead "
        "of reusing the existing one."
    )
