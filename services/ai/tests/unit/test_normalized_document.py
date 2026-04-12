"""Smoke tests for the normalized document schema (Pydantic models).

These tests verify that the models can be instantiated and behave correctly
at a basic level.  No parsing or database involvement.
"""

import pytest

from app.schemas.normalized_document import (
    BlockPosition,
    BlockType,
    DocumentBlock,
    DocumentChunk,
    DocumentType,
    LectureSlidesMetadata,
    LectureNotesMetadata,
    NormalizedDocument,
    PastExamMetadata,
    ReferenceMetadata,
    TextbookExcerptMetadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_block(block_type: BlockType, text: str, page: int = 1) -> DocumentBlock:
    return DocumentBlock(
        block_type=block_type,
        text=text,
        position=BlockPosition(page=page, section_path=["Section 1"]),
    )


def _make_doc(**kwargs) -> NormalizedDocument:
    defaults = dict(
        doc_id="doc-001",
        course_id="course-001",
        document_type=DocumentType.LECTURE_NOTES,
        title="Test Doc",
        source_filename="test.pdf",
        parser_used="test-parser",
        blocks=[],
    )
    defaults.update(kwargs)
    return NormalizedDocument(**defaults)


# ---------------------------------------------------------------------------
# BlockPosition
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_block_position_defaults():
    pos = BlockPosition()
    assert pos.page is None
    assert pos.slide is None
    assert pos.section_path == []
    assert pos.paragraph_index is None


@pytest.mark.unit
def test_block_position_with_values():
    pos = BlockPosition(page=3, section_path=["Ch1", "1.2"])
    assert pos.page == 3
    assert pos.section_path == ["Ch1", "1.2"]


# ---------------------------------------------------------------------------
# DocumentBlock
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_document_block_created():
    block = _make_block(BlockType.PARAGRAPH, "Hello world")
    assert block.block_type == BlockType.PARAGRAPH
    assert block.text == "Hello world"
    assert block.block_id is not None


@pytest.mark.unit
def test_document_block_heading_level():
    block = DocumentBlock(
        block_type=BlockType.HEADING,
        text="Chapter 1",
        position=BlockPosition(page=1),
        heading_level=1,
    )
    assert block.heading_level == 1


@pytest.mark.unit
def test_document_block_exam_question_fields():
    block = DocumentBlock(
        block_type=BlockType.EXAM_QUESTION,
        text="What is a hash function?",
        position=BlockPosition(page=1),
        question_number="Q1",
        marks=5,
    )
    assert block.question_number == "Q1"
    assert block.marks == 5


@pytest.mark.unit
def test_document_block_ids_are_unique():
    b1 = _make_block(BlockType.PARAGRAPH, "A")
    b2 = _make_block(BlockType.PARAGRAPH, "B")
    assert b1.block_id != b2.block_id


# ---------------------------------------------------------------------------
# NormalizedDocument
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_normalized_document_created():
    doc = _make_doc()
    assert doc.doc_id == "doc-001"
    assert doc.document_type == DocumentType.LECTURE_NOTES
    assert doc.blocks == []


@pytest.mark.unit
def test_normalized_document_language_default():
    doc = _make_doc()
    assert doc.language == "en"


@pytest.mark.unit
def test_normalized_document_blocks_for_page():
    blocks = [
        _make_block(BlockType.PARAGRAPH, "p1", page=1),
        _make_block(BlockType.PARAGRAPH, "p2", page=2),
        _make_block(BlockType.PARAGRAPH, "p3", page=1),
    ]
    doc = _make_doc(blocks=blocks)
    assert len(doc.blocks_for_page(1)) == 2
    assert len(doc.blocks_for_page(2)) == 1
    assert len(doc.blocks_for_page(99)) == 0


@pytest.mark.unit
def test_normalized_document_blocks_for_slide():
    blocks = [
        DocumentBlock(
            block_type=BlockType.SLIDE_TITLE,
            text="Slide 1 title",
            position=BlockPosition(slide=1),
        ),
        DocumentBlock(
            block_type=BlockType.SLIDE_BODY,
            text="Slide 2 body",
            position=BlockPosition(slide=2),
        ),
    ]
    doc = _make_doc(document_type=DocumentType.LECTURE_SLIDES, blocks=blocks)
    assert len(doc.blocks_for_slide(1)) == 1
    assert len(doc.blocks_for_slide(2)) == 1


@pytest.mark.unit
def test_normalized_document_heading_blocks():
    blocks = [
        _make_block(BlockType.HEADING, "Title"),
        _make_block(BlockType.PARAGRAPH, "Body"),
        _make_block(BlockType.HEADING, "Subtitle"),
    ]
    doc = _make_doc(blocks=blocks)
    headings = doc.heading_blocks()
    assert len(headings) == 2
    assert all(b.block_type == BlockType.HEADING for b in headings)


@pytest.mark.unit
def test_normalized_document_typed_metadata_lecture_slides():
    meta = LectureSlidesMetadata(lecture_number=3, total_slides=12)
    doc = _make_doc(
        document_type=DocumentType.LECTURE_SLIDES,
        type_metadata=meta.model_dump(),
    )
    result = doc.typed_metadata()
    assert isinstance(result, LectureSlidesMetadata)
    assert result.lecture_number == 3
    assert result.total_slides == 12


@pytest.mark.unit
def test_normalized_document_typed_metadata_returns_none_when_absent():
    doc = _make_doc(type_metadata=None)
    assert doc.typed_metadata() is None


# ---------------------------------------------------------------------------
# DocumentChunk.from_blocks
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chunk_from_page_blocks():
    blocks = [
        _make_block(BlockType.PARAGRAPH, "First sentence.", page=5),
        _make_block(BlockType.PARAGRAPH, "Second sentence.", page=5),
    ]
    doc = _make_doc(blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0)

    assert "First sentence." in chunk.text
    assert "Second sentence." in chunk.text
    assert chunk.citation_page == 5
    assert chunk.citation_label == "p. 5"
    assert chunk.chunk_index == 0
    assert len(chunk.block_ids) == 2


@pytest.mark.unit
def test_chunk_from_slide_blocks():
    blocks = [
        DocumentBlock(
            block_type=BlockType.SLIDE_TITLE,
            text="Hash Functions",
            position=BlockPosition(slide=7, section_path=[]),
        )
    ]
    doc = _make_doc(document_type=DocumentType.LECTURE_SLIDES, blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=2)

    assert chunk.citation_slide == 7
    assert chunk.citation_label == "Slide 7"
    assert chunk.chunk_index == 2


@pytest.mark.unit
def test_chunk_from_empty_blocks_raises():
    doc = _make_doc()
    with pytest.raises(ValueError):
        DocumentChunk.from_blocks([], doc, chunk_index=0)


@pytest.mark.unit
def test_chunk_char_count():
    text = "Exactly twenty chars"
    blocks = [_make_block(BlockType.PARAGRAPH, text)]
    doc = _make_doc(blocks=blocks)
    chunk = DocumentChunk.from_blocks(blocks, doc, chunk_index=0)
    assert chunk.char_count == len(text)


# ---------------------------------------------------------------------------
# Source-type metadata models
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_textbook_excerpt_metadata():
    meta = TextbookExcerptMetadata(
        book_title="Mastering Bitcoin",
        authors=["Antonopoulos"],
        chapter="Chapter 4",
    )
    assert meta.book_title == "Mastering Bitcoin"
    assert meta.authors == ["Antonopoulos"]
    assert meta.isbn is None


@pytest.mark.unit
def test_past_exam_metadata_defaults():
    meta = PastExamMetadata()
    assert meta.with_solutions is False
    assert meta.total_marks is None


@pytest.mark.unit
def test_reference_metadata_bip():
    meta = ReferenceMetadata(title="BIP-340", bip_number=340)
    assert meta.bip_number == 340


@pytest.mark.unit
def test_lecture_notes_metadata_topics():
    meta = LectureNotesMetadata(topics=["ECDSA", "Schnorr"])
    assert len(meta.topics) == 2
