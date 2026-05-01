"""Unit tests for DocumentChunk and NormalizedDocument schema extensions (R-01).

Covers:
- lecture_id / tags / prerequisites fields on NormalizedDocument
- from_blocks() propagation of those fields into DocumentChunk
- chunk_type and parent_chunk_id hierarchy fields
- Chroma metadata completeness (all 12 fields present)
"""
import pytest

from app.schemas.normalized_document import (
    BlockPosition,
    BlockType,
    ChunkType,
    DocumentBlock,
    DocumentChunk,
    DocumentType,
    NormalizedDocument,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block(text: str, page: int = 1, section: str = "Intro") -> DocumentBlock:
    return DocumentBlock(
        block_type=BlockType.PARAGRAPH,
        text=text,
        position=BlockPosition(page=page, section_path=[section]),
    )


def _heading(text: str, page: int = 1) -> DocumentBlock:
    return DocumentBlock(
        block_type=BlockType.HEADING,
        text=text,
        position=BlockPosition(page=page),
        heading_level=1,
    )


def _doc(**kwargs) -> NormalizedDocument:
    defaults = dict(
        doc_id="doc-001",
        course_id="course-001",
        document_type=DocumentType.LECTURE_NOTES,
        title="Test",
        source_filename="test.pdf",
        parser_used="test",
        blocks=[],
    )
    defaults.update(kwargs)
    return NormalizedDocument(**defaults)


# ---------------------------------------------------------------------------
# NormalizedDocument — new fields
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_normalized_document_lecture_id_default_none():
    doc = _doc()
    assert doc.lecture_id is None


@pytest.mark.unit
def test_normalized_document_lecture_id_set():
    doc = _doc(lecture_id="L03")
    assert doc.lecture_id == "L03"


@pytest.mark.unit
def test_normalized_document_tags_default_empty():
    doc = _doc()
    assert doc.tags == []


@pytest.mark.unit
def test_normalized_document_tags_set():
    doc = _doc(tags=["cryptography", "hashing"])
    assert doc.tags == ["cryptography", "hashing"]


@pytest.mark.unit
def test_normalized_document_prerequisites_default_empty():
    doc = _doc()
    assert doc.prerequisites == []


@pytest.mark.unit
def test_normalized_document_prerequisites_set():
    doc = _doc(prerequisites=["elliptic-curves", "sha256"])
    assert len(doc.prerequisites) == 2


# ---------------------------------------------------------------------------
# DocumentChunk — new fields present
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chunk_has_lecture_id_field():
    chunk = DocumentChunk(
        doc_id="d",
        course_id="c",
        lecture_id="L01",
        document_type=DocumentType.LECTURE_NOTES,
        text="hello",
        block_ids=["b1"],
        citation_label="p. 1",
        chunk_index=0,
        char_count=5,
    )
    assert chunk.lecture_id == "L01"


@pytest.mark.unit
def test_chunk_has_tags_field():
    chunk = DocumentChunk(
        doc_id="d",
        course_id="c",
        document_type=DocumentType.LECTURE_NOTES,
        text="hello",
        block_ids=["b1"],
        citation_label="p. 1",
        chunk_index=0,
        char_count=5,
        tags=["mining", "difficulty"],
    )
    assert chunk.tags == ["mining", "difficulty"]


@pytest.mark.unit
def test_chunk_has_prerequisites_field():
    chunk = DocumentChunk(
        doc_id="d",
        course_id="c",
        document_type=DocumentType.LECTURE_NOTES,
        text="hello",
        block_ids=["b1"],
        citation_label="p. 1",
        chunk_index=0,
        char_count=5,
        prerequisites=["hash-functions"],
    )
    assert chunk.prerequisites == ["hash-functions"]


@pytest.mark.unit
def test_chunk_chunk_type_default():
    chunk = DocumentChunk(
        doc_id="d",
        course_id="c",
        document_type=DocumentType.LECTURE_NOTES,
        text="hello",
        block_ids=["b1"],
        citation_label="p. 1",
        chunk_index=0,
        char_count=5,
    )
    assert chunk.chunk_type == ChunkType.PARAGRAPH


@pytest.mark.unit
def test_chunk_parent_chunk_id_default_none():
    chunk = DocumentChunk(
        doc_id="d",
        course_id="c",
        document_type=DocumentType.LECTURE_NOTES,
        text="hello",
        block_ids=["b1"],
        citation_label="p. 1",
        chunk_index=0,
        char_count=5,
    )
    assert chunk.parent_chunk_id is None


# ---------------------------------------------------------------------------
# from_blocks() — propagation of lecture_id / tags / prerequisites
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_from_blocks_propagates_lecture_id():
    blocks = [_block("text")]
    doc = _doc(lecture_id="L05", blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0)
    assert chunk.lecture_id == "L05"


@pytest.mark.unit
def test_from_blocks_propagates_tags():
    blocks = [_block("text")]
    doc = _doc(tags=["utxo", "scripts"], blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0)
    assert chunk.tags == ["utxo", "scripts"]


@pytest.mark.unit
def test_from_blocks_propagates_prerequisites():
    blocks = [_block("text")]
    doc = _doc(prerequisites=["hash-functions", "ecdsa"], blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0)
    assert chunk.prerequisites == ["hash-functions", "ecdsa"]


@pytest.mark.unit
def test_from_blocks_lecture_id_none_when_doc_has_none():
    blocks = [_block("text")]
    doc = _doc(blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0)
    assert chunk.lecture_id is None


@pytest.mark.unit
def test_from_blocks_tags_isolated_from_doc():
    """Mutating the returned chunk's tags should not affect the document."""
    blocks = [_block("text")]
    doc = _doc(tags=["utxo"], blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0)
    chunk.tags.append("injected")
    assert doc.tags == ["utxo"]


@pytest.mark.unit
def test_from_blocks_chunk_type_section():
    blocks = [_heading("Introduction"), _block("body")]
    doc = _doc(blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0, chunk_type=ChunkType.SECTION)
    assert chunk.chunk_type == ChunkType.SECTION


@pytest.mark.unit
def test_from_blocks_chunk_type_micro():
    blocks = [_block("short")]
    doc = _doc(blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0, chunk_type=ChunkType.MICRO)
    assert chunk.chunk_type == ChunkType.MICRO


@pytest.mark.unit
def test_from_blocks_parent_chunk_id_propagated():
    blocks = [_block("text")]
    doc = _doc(blocks=blocks)
    parent_id = "parent-uuid-1234"
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=1, parent_chunk_id=parent_id)
    assert chunk.parent_chunk_id == parent_id


# ---------------------------------------------------------------------------
# Chroma metadata completeness
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chunk_chroma_metadata_all_fields_serialisable():
    """All fields required by retrieval_2_embedder must be present and serialisable."""
    blocks = [_block("text", page=3, section="Merkle Trees")]
    doc = _doc(
        lecture_id="L02",
        tags=["merkle", "hashing"],
        prerequisites=["sha256"],
        blocks=blocks,
    )
    chunk = DocumentChunk.from_blocks(
        blocks, doc, chunk_index=0,
        chunk_type=ChunkType.PARAGRAPH,
        parent_chunk_id="parent-1",
    )

    # Build metadata exactly as retrieval_2_embedder.py does
    meta = {
        "doc_id": chunk.doc_id,
        "course_id": chunk.course_id,
        "lecture_id": chunk.lecture_id or chunk.doc_id,
        "document_type": chunk.document_type.value,
        "label": chunk.citation_label,
        "section": chunk.citation_section or "N/A",
        "page": chunk.citation_page or 0,
        "slide": chunk.citation_slide or 0,
        "chunk_type": chunk.chunk_type.value,
        "parent_chunk_id": chunk.parent_chunk_id or "",
        "tags": ",".join(chunk.tags),
        "prerequisites": ",".join(chunk.prerequisites),
    }

    assert meta["lecture_id"] == "L02"
    assert meta["tags"] == "merkle,hashing"
    assert meta["prerequisites"] == "sha256"
    assert meta["chunk_type"] == "paragraph"
    assert meta["parent_chunk_id"] == "parent-1"
    assert meta["page"] == 3
    assert len(meta) == 12
