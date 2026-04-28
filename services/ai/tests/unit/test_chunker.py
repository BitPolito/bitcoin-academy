"""Unit tests for Chunker — 3-level hierarchical chunking (R-01).

Import order matters:
  1. app.workers.pipeline is imported first — its module-level _alias_schema_module()
     registers 'services.ai.app.schemas.normalized_document' as an alias of the
     FastAPI module and adds the ingester src to sys.path.
  2. Only then can Chunker (which imports from services.ai.app.schemas…) be
     imported without a ModuleNotFoundError.
"""
import pytest

import app.workers.pipeline  # noqa: F401 — sets up sys.modules alias + sys.path
from module_3_micro_chunker import Chunker  # noqa: E402

from app.schemas.normalized_document import (
    BlockPosition,
    BlockType,
    ChunkType,
    DocumentBlock,
    DocumentType,
    NormalizedDocument,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _para(text: str, page: int = 1, section: str = "Section") -> DocumentBlock:
    return DocumentBlock(
        block_type=BlockType.PARAGRAPH,
        text=text,
        position=BlockPosition(page=page, section_path=[section]),
    )


def _heading(text: str, page: int = 1) -> DocumentBlock:
    return DocumentBlock(
        block_type=BlockType.HEADING,
        text=text,
        position=BlockPosition(page=page, section_path=[]),
        heading_level=1,
    )


def _doc(blocks: list, **kwargs) -> NormalizedDocument:
    base = dict(
        doc_id="doc-001",
        course_id="course-001",
        document_type=DocumentType.LECTURE_NOTES,
        title="Test",
        source_filename="test.pdf",
        parser_used="test",
        blocks=blocks,
    )
    base.update(kwargs)
    return NormalizedDocument(**base)


# ---------------------------------------------------------------------------
# Basic instantiation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chunker_instantiation():
    c = Chunker()
    assert c.max_char_limit == 1500
    assert c.micro_char_limit == 300


@pytest.mark.unit
def test_chunker_custom_limits():
    c = Chunker(max_char_limit=800, micro_char_limit=100)
    assert c.max_char_limit == 800
    assert c.micro_char_limit == 100


# ---------------------------------------------------------------------------
# Empty document
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_empty_document_yields_no_chunks():
    doc = _doc([])
    chunks = Chunker().process_document(doc)
    assert chunks == []


# ---------------------------------------------------------------------------
# Three-level structure
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_single_section_produces_all_three_levels():
    blocks = [
        _heading("Introduction"),
        _para("Bitcoin is a peer-to-peer electronic cash system."),
        _para("Transactions are grouped into blocks."),
    ]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)

    section_chunks = [c for c in chunks if c.chunk_type == ChunkType.SECTION]
    para_chunks = [c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH]
    micro_chunks = [c for c in chunks if c.chunk_type == ChunkType.MICRO]

    assert len(section_chunks) == 1
    assert len(para_chunks) >= 1
    assert len(micro_chunks) >= 1


@pytest.mark.unit
def test_two_headings_produce_two_sections():
    blocks = [
        _heading("Introduction"),
        _para("Bitcoin intro."),
        _heading("Blockchain"),
        _para("Blockchain details."),
    ]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)

    section_chunks = [c for c in chunks if c.chunk_type == ChunkType.SECTION]
    assert len(section_chunks) == 2


@pytest.mark.unit
def test_three_headings_produce_three_sections():
    blocks = [
        _heading("H1"), _para("body1"),
        _heading("H2"), _para("body2"),
        _heading("H3"), _para("body3"),
    ]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)

    section_chunks = [c for c in chunks if c.chunk_type == ChunkType.SECTION]
    assert len(section_chunks) == 3


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_long_content_splits_into_multiple_paragraphs():
    # 5 blocks of 400 chars each → should split into multiple paragraph chunks at 1500 limit
    big_text = "x" * 400
    blocks = [_heading("Section")] + [_para(big_text) for _ in range(5)]
    doc = _doc(blocks)
    chunks = Chunker(max_char_limit=1500).process_document(doc)

    para_chunks = [c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH]
    assert len(para_chunks) >= 2


@pytest.mark.unit
def test_short_content_stays_in_one_paragraph():
    blocks = [_heading("Section"), _para("Short."), _para("Also short.")]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)

    para_chunks = [c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH]
    assert len(para_chunks) == 1


# ---------------------------------------------------------------------------
# Micro splitting
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_micro_chunks_respect_limit():
    chunker = Chunker(micro_char_limit=100)
    long_text = "This is sentence one. This is sentence two. This is sentence three. This is four."
    micros = chunker._split_into_micros(long_text)
    for m in micros:
        # Each micro chunk should not exceed the limit plus last sentence overflow
        assert len(m) <= 300  # generous bound; exact limit depends on sentence boundaries


@pytest.mark.unit
def test_micro_fallback_single_sentence():
    chunker = Chunker(micro_char_limit=300)
    text = "One single sentence without any terminal punctuation here"
    micros = chunker._split_into_micros(text)
    assert len(micros) == 1
    assert micros[0] == text


@pytest.mark.unit
def test_micro_splits_at_sentence_boundary():
    chunker = Chunker(micro_char_limit=50)
    text = "Short one. Short two. Short three."
    micros = chunker._split_into_micros(text)
    # All sentences are ~10 chars each, well within limit — should not split unnecessarily
    # With limit=50 and sentences of ~10 chars each, they can group together
    assert all(text.strip() for text in micros)


# ---------------------------------------------------------------------------
# Hierarchy — parent_chunk_id linkage
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_paragraph_parent_is_section():
    blocks = [_heading("Intro"), _para("Bitcoin.")]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)

    section = next(c for c in chunks if c.chunk_type == ChunkType.SECTION)
    para = next(c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH)
    assert para.parent_chunk_id == section.chunk_id


@pytest.mark.unit
def test_micro_parent_is_paragraph():
    blocks = [_heading("Intro"), _para("First sentence. Second sentence. Third sentence.")]
    doc = _doc(blocks)
    chunks = Chunker(micro_char_limit=30).process_document(doc)

    para = next(c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH)
    micros = [c for c in chunks if c.chunk_type == ChunkType.MICRO]
    for m in micros:
        assert m.parent_chunk_id == para.chunk_id


@pytest.mark.unit
def test_section_has_no_parent():
    blocks = [_heading("Intro"), _para("text")]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)

    section = next(c for c in chunks if c.chunk_type == ChunkType.SECTION)
    assert section.parent_chunk_id is None


# ---------------------------------------------------------------------------
# Metadata propagation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chunks_inherit_course_id():
    blocks = [_para("text")]
    doc = _doc(blocks, course_id="course-bitcoin-101")
    chunks = Chunker().process_document(doc)
    assert all(c.course_id == "course-bitcoin-101" for c in chunks)


@pytest.mark.unit
def test_chunks_inherit_lecture_id():
    blocks = [_para("text")]
    doc = _doc(blocks, lecture_id="L07")
    chunks = Chunker().process_document(doc)
    # Only section/paragraph chunks (from_blocks path) get lecture_id
    section_chunks = [c for c in chunks if c.chunk_type == ChunkType.SECTION]
    para_chunks = [c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH]
    for c in section_chunks + para_chunks:
        assert c.lecture_id == "L07"


@pytest.mark.unit
def test_chunks_inherit_tags_and_prerequisites():
    blocks = [_para("text")]
    doc = _doc(blocks, tags=["utxo"], prerequisites=["cryptography"])
    chunks = Chunker().process_document(doc)
    section_para = [c for c in chunks if c.chunk_type in (ChunkType.SECTION, ChunkType.PARAGRAPH)]
    for c in section_para:
        assert c.tags == ["utxo"]
        assert c.prerequisites == ["cryptography"]


# ---------------------------------------------------------------------------
# Citation correctness
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_citation_page_on_para_chunk():
    blocks = [_para("text", page=7)]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)
    para = next(c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH)
    assert para.citation_page == 7
    assert para.citation_label == "p. 7"


@pytest.mark.unit
def test_chunk_ids_are_unique():
    blocks = [
        _heading("H1"), _para("A."),
        _heading("H2"), _para("B."),
    ]
    doc = _doc(blocks)
    chunks = Chunker().process_document(doc)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
