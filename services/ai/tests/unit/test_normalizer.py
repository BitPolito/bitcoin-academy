"""Smoke tests for app/rag/normalizer.py.

Verifies that the dispatch function and each per-type normalizer produce a
valid NormalizedDocument from minimal parser output.
"""

import pytest

from app.rag.normalizer import normalize
from app.schemas.normalized_document import (
    BlockType,
    DocumentType,
    LectureSlidesMetadata,
    LectureNotesMetadata,
    NormalizedDocument,
    PastExamMetadata,
    ReferenceMetadata,
    TextbookExcerptMetadata,
)


# ---------------------------------------------------------------------------
# Shared minimal parser outputs
# ---------------------------------------------------------------------------

_ONE_SLIDE = {
    "title": "Lecture 1",
    "slides": [
        {
            "number": 1,
            "blocks": [
                {"type": "slide_title", "text": "Hash Functions", "section_path": []},
                {"type": "slide_body", "text": "SHA-256 produces a 32-byte digest.", "section_path": ["Hash Functions"]},
            ],
        }
    ],
    "metadata": {"lecture_number": 1, "course_name": "Bitcoin"},
}

_ONE_PAGE = {
    "title": "Lecture 2 Notes",
    "pages": [
        {
            "number": 1,
            "blocks": [
                {"type": "heading", "text": "Private Keys", "heading_level": 1, "section_path": []},
                {"type": "paragraph", "text": "A private key is a random 256-bit number.", "section_path": ["Private Keys"]},
            ],
        }
    ],
    "metadata": {"lecture_number": 2, "course_name": "Bitcoin", "topics": ["Keys"]},
}

_TEXTBOOK = {
    "title": "Mastering Bitcoin — Ch4",
    "pages": [
        {
            "number": 67,
            "blocks": [
                {"type": "paragraph", "text": "A private key is simply a number.", "section_path": ["Chapter 4"]},
            ],
        }
    ],
    "metadata": {
        "book_title": "Mastering Bitcoin",
        "authors": ["Antonopoulos"],
        "chapter": "Chapter 4",
    },
}

_EXAM = {
    "title": "Final Exam 2025",
    "pages": [
        {
            "number": 1,
            "blocks": [
                {"type": "exam_question", "text": "What is SHA-256?", "question_number": "Q1", "marks": 3, "section_path": []},
            ],
        }
    ],
    "metadata": {"course_name": "Bitcoin", "total_marks": 30, "with_solutions": False},
}

_REFERENCE = {
    "title": "Bitcoin: A Peer-to-Peer Electronic Cash System",
    "pages": [
        {
            "number": 1,
            "blocks": [
                {"type": "paragraph", "text": "A purely peer-to-peer version of electronic cash.", "section_path": []},
            ],
        }
    ],
    "metadata": {"authors": ["Satoshi Nakamoto"], "published_date": "2008-10-31"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(doc_type: DocumentType, parser_output: dict) -> NormalizedDocument:
    return normalize(
        document_type=doc_type,
        parser_output=parser_output,
        doc_id="doc-test",
        course_id="course-test",
        source_filename="test.pdf",
        parser_used="test-parser",
    )


# ---------------------------------------------------------------------------
# Common contract: every normalizer must return a valid NormalizedDocument
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("doc_type,parser_output", [
    (DocumentType.LECTURE_SLIDES, _ONE_SLIDE),
    (DocumentType.LECTURE_NOTES, _ONE_PAGE),
    (DocumentType.TEXTBOOK_EXCERPT, _TEXTBOOK),
    (DocumentType.PAST_EXAM, _EXAM),
    (DocumentType.REFERENCE, _REFERENCE),
])
def test_normalize_returns_normalized_document(doc_type, parser_output):
    doc = _normalize(doc_type, parser_output)
    assert isinstance(doc, NormalizedDocument)
    assert doc.doc_id == "doc-test"
    assert doc.course_id == "course-test"
    assert doc.document_type == doc_type
    assert len(doc.blocks) > 0
    assert doc.word_count is not None and doc.word_count > 0


# ---------------------------------------------------------------------------
# Lecture slides
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_lecture_slides_block_types():
    doc = _normalize(DocumentType.LECTURE_SLIDES, _ONE_SLIDE)
    types = {b.block_type for b in doc.blocks}
    assert BlockType.SLIDE_TITLE in types
    assert BlockType.SLIDE_BODY in types


@pytest.mark.unit
def test_lecture_slides_slide_numbers():
    doc = _normalize(DocumentType.LECTURE_SLIDES, _ONE_SLIDE)
    assert all(b.position.slide == 1 for b in doc.blocks)
    assert all(b.position.page is None for b in doc.blocks)


@pytest.mark.unit
def test_lecture_slides_typed_metadata():
    doc = _normalize(DocumentType.LECTURE_SLIDES, _ONE_SLIDE)
    meta = doc.typed_metadata()
    assert isinstance(meta, LectureSlidesMetadata)
    assert meta.lecture_number == 1
    assert meta.total_slides == 1


# ---------------------------------------------------------------------------
# Lecture notes
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_lecture_notes_page_numbers():
    doc = _normalize(DocumentType.LECTURE_NOTES, _ONE_PAGE)
    assert all(b.position.page == 1 for b in doc.blocks)
    assert all(b.position.slide is None for b in doc.blocks)


@pytest.mark.unit
def test_lecture_notes_typed_metadata():
    doc = _normalize(DocumentType.LECTURE_NOTES, _ONE_PAGE)
    meta = doc.typed_metadata()
    assert isinstance(meta, LectureNotesMetadata)
    assert meta.topics == ["Keys"]


# ---------------------------------------------------------------------------
# Textbook excerpt
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_textbook_page_numbers():
    doc = _normalize(DocumentType.TEXTBOOK_EXCERPT, _TEXTBOOK)
    assert doc.blocks[0].position.page == 67


@pytest.mark.unit
def test_textbook_typed_metadata():
    doc = _normalize(DocumentType.TEXTBOOK_EXCERPT, _TEXTBOOK)
    meta = doc.typed_metadata()
    assert isinstance(meta, TextbookExcerptMetadata)
    assert meta.book_title == "Mastering Bitcoin"
    assert meta.start_page == 67
    assert meta.end_page == 67


# ---------------------------------------------------------------------------
# Past exam
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_past_exam_question_block():
    doc = _normalize(DocumentType.PAST_EXAM, _EXAM)
    q_blocks = [b for b in doc.blocks if b.block_type == BlockType.EXAM_QUESTION]
    assert len(q_blocks) == 1
    assert q_blocks[0].question_number == "Q1"
    assert q_blocks[0].marks == 3


@pytest.mark.unit
def test_past_exam_typed_metadata():
    doc = _normalize(DocumentType.PAST_EXAM, _EXAM)
    meta = doc.typed_metadata()
    assert isinstance(meta, PastExamMetadata)
    assert meta.total_marks == 30
    assert meta.with_solutions is False


# ---------------------------------------------------------------------------
# Reference document
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_reference_typed_metadata():
    doc = _normalize(DocumentType.REFERENCE, _REFERENCE)
    meta = doc.typed_metadata()
    assert isinstance(meta, ReferenceMetadata)
    assert "Satoshi Nakamoto" in meta.authors


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_normalize_empty_pages_gives_no_blocks():
    empty = {"title": "Empty", "pages": [], "metadata": {"book_title": "X"}}
    doc = _normalize(DocumentType.TEXTBOOK_EXCERPT, empty)
    assert doc.blocks == []


@pytest.mark.unit
def test_normalize_unknown_block_type_falls_back_to_paragraph():
    output = {
        "title": "Test",
        "pages": [{"number": 1, "blocks": [{"type": "unknown_type", "text": "Some text"}]}],
        "metadata": {},
    }
    doc = _normalize(DocumentType.LECTURE_NOTES, output)
    assert doc.blocks[0].block_type == BlockType.PARAGRAPH


@pytest.mark.unit
def test_normalize_section_path_preserved():
    output = {
        "title": "Test",
        "pages": [
            {
                "number": 1,
                "blocks": [
                    {"type": "paragraph", "text": "X", "section_path": ["Ch1", "1.1"]},
                ],
            }
        ],
        "metadata": {},
    }
    doc = _normalize(DocumentType.LECTURE_NOTES, output)
    assert doc.blocks[0].position.section_path == ["Ch1", "1.1"]
