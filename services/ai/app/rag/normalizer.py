"""Normalizer — maps raw parser output to NormalizedDocument.

Each parser (PyMuPDF, python-pptx, …) returns an untyped dict.  The
normalizer functions in this module convert those dicts into fully-typed
NormalizedDocument instances.

Parser output contract (what every parser must return):
    {
        "title": str,
        "pages": [                       # or "slides" for PPTX
            {
                "number": int,           # 1-indexed
                "blocks": [
                    {
                        "type": str,     # maps to BlockType value
                        "text": str,
                        # optional extras:
                        "heading_level": int,
                        "language": str,
                        "question_number": str,
                        "marks": int,
                        "table_markdown": str,
                        "section_path": [str],
                        "paragraph_index": int,
                    }
                ]
            }
        ],
        "metadata": dict,                # free-form parser extras
    }

Normalizer functions accept that dict plus doc-level identifiers and return
a NormalizedDocument ready for the chunking stage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.schemas.normalized_document import (
    BlockPosition,
    BlockType,
    DocumentBlock,
    DocumentType,
    LectureSlidesMetadata,
    LectureNotesMetadata,
    NormalizedDocument,
    PastExamMetadata,
    ReferenceMetadata,
    TextbookExcerptMetadata,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_block(raw: Dict[str, Any], page: int | None, slide: int | None) -> DocumentBlock:
    """Convert one raw parser block dict into a DocumentBlock."""
    try:
        block_type = BlockType(raw["type"])
    except ValueError:
        block_type = BlockType.PARAGRAPH  # safe fallback

    position = BlockPosition(
        page=page,
        slide=slide,
        section_path=raw.get("section_path", []),
        paragraph_index=raw.get("paragraph_index"),
    )

    return DocumentBlock(
        block_type=block_type,
        text=raw.get("text", "").strip(),
        position=position,
        heading_level=raw.get("heading_level"),
        language=raw.get("language"),
        question_number=raw.get("question_number"),
        marks=raw.get("marks"),
        table_markdown=raw.get("table_markdown"),
    )


def _count_words(blocks: List[DocumentBlock]) -> int:
    return sum(len(b.text.split()) for b in blocks)


# ---------------------------------------------------------------------------
# Per-type normalizers
# ---------------------------------------------------------------------------


def normalize_lecture_slides(
    parser_output: Dict[str, Any],
    doc_id: str,
    course_id: str,
    source_filename: str,
    parser_used: str,
) -> NormalizedDocument:
    """Map PPTX / slide-PDF parser output to NormalizedDocument."""
    slides_raw = parser_output.get("slides", parser_output.get("pages", []))
    blocks: List[DocumentBlock] = []

    for slide_raw in slides_raw:
        slide_num = slide_raw.get("number", slide_raw.get("slide", 1))
        for block_raw in slide_raw.get("blocks", []):
            blocks.append(_build_block(block_raw, page=None, slide=slide_num))

    raw_meta = parser_output.get("metadata", {})
    type_meta = LectureSlidesMetadata(
        course_name=raw_meta.get("course_name"),
        lecture_number=raw_meta.get("lecture_number"),
        total_slides=len(slides_raw),
    )

    return NormalizedDocument(
        doc_id=doc_id,
        course_id=course_id,
        document_type=DocumentType.LECTURE_SLIDES,
        title=parser_output.get("title", source_filename),
        source_filename=source_filename,
        parser_used=parser_used,
        parsed_at=datetime.now(),
        slide_count=len(slides_raw),
        word_count=_count_words(blocks),
        blocks=blocks,
        type_metadata=type_meta.model_dump(),
        raw_metadata=raw_meta,
    )


def normalize_lecture_notes(
    parser_output: Dict[str, Any],
    doc_id: str,
    course_id: str,
    source_filename: str,
    parser_used: str,
) -> NormalizedDocument:
    """Map PDF/DOCX lecture notes parser output to NormalizedDocument."""
    pages_raw = parser_output.get("pages", [])
    blocks: List[DocumentBlock] = []

    for page_raw in pages_raw:
        page_num = page_raw.get("number", page_raw.get("page", 1))
        for block_raw in page_raw.get("blocks", []):
            blocks.append(_build_block(block_raw, page=page_num, slide=None))

    raw_meta = parser_output.get("metadata", {})
    type_meta = LectureNotesMetadata(
        course_name=raw_meta.get("course_name"),
        lecture_number=raw_meta.get("lecture_number"),
        topics=raw_meta.get("topics", []),
    )

    return NormalizedDocument(
        doc_id=doc_id,
        course_id=course_id,
        document_type=DocumentType.LECTURE_NOTES,
        title=parser_output.get("title", source_filename),
        source_filename=source_filename,
        parser_used=parser_used,
        parsed_at=datetime.now(),
        page_count=len(pages_raw),
        word_count=_count_words(blocks),
        blocks=blocks,
        type_metadata=type_meta.model_dump(),
        raw_metadata=raw_meta,
    )


def normalize_textbook_excerpt(
    parser_output: Dict[str, Any],
    doc_id: str,
    course_id: str,
    source_filename: str,
    parser_used: str,
) -> NormalizedDocument:
    """Map textbook PDF parser output to NormalizedDocument."""
    pages_raw = parser_output.get("pages", [])
    blocks: List[DocumentBlock] = []

    for page_raw in pages_raw:
        page_num = page_raw.get("number", page_raw.get("page", 1))
        for block_raw in page_raw.get("blocks", []):
            blocks.append(_build_block(block_raw, page=page_num, slide=None))

    raw_meta = parser_output.get("metadata", {})
    type_meta = TextbookExcerptMetadata(
        book_title=raw_meta.get("book_title", parser_output.get("title", "")),
        authors=raw_meta.get("authors", []),
        edition=raw_meta.get("edition"),
        chapter=raw_meta.get("chapter"),
        isbn=raw_meta.get("isbn"),
        start_page=pages_raw[0].get("number") if pages_raw else None,
        end_page=pages_raw[-1].get("number") if pages_raw else None,
    )

    return NormalizedDocument(
        doc_id=doc_id,
        course_id=course_id,
        document_type=DocumentType.TEXTBOOK_EXCERPT,
        title=parser_output.get("title", source_filename),
        source_filename=source_filename,
        parser_used=parser_used,
        parsed_at=datetime.now(),
        page_count=len(pages_raw),
        word_count=_count_words(blocks),
        blocks=blocks,
        type_metadata=type_meta.model_dump(),
        raw_metadata=raw_meta,
    )


def normalize_past_exam(
    parser_output: Dict[str, Any],
    doc_id: str,
    course_id: str,
    source_filename: str,
    parser_used: str,
) -> NormalizedDocument:
    """Map exam PDF parser output to NormalizedDocument."""
    pages_raw = parser_output.get("pages", [])
    blocks: List[DocumentBlock] = []

    for page_raw in pages_raw:
        page_num = page_raw.get("number", page_raw.get("page", 1))
        for block_raw in page_raw.get("blocks", []):
            blocks.append(_build_block(block_raw, page=page_num, slide=None))

    raw_meta = parser_output.get("metadata", {})
    type_meta = PastExamMetadata(
        course_name=raw_meta.get("course_name"),
        exam_date=raw_meta.get("exam_date"),
        academic_year=raw_meta.get("academic_year"),
        duration_minutes=raw_meta.get("duration_minutes"),
        total_marks=raw_meta.get("total_marks"),
        with_solutions=raw_meta.get("with_solutions", False),
    )

    return NormalizedDocument(
        doc_id=doc_id,
        course_id=course_id,
        document_type=DocumentType.PAST_EXAM,
        title=parser_output.get("title", source_filename),
        source_filename=source_filename,
        parser_used=parser_used,
        parsed_at=datetime.now(),
        page_count=len(pages_raw),
        word_count=_count_words(blocks),
        blocks=blocks,
        type_metadata=type_meta.model_dump(),
        raw_metadata=raw_meta,
    )


def normalize_reference(
    parser_output: Dict[str, Any],
    doc_id: str,
    course_id: str,
    source_filename: str,
    parser_used: str,
) -> NormalizedDocument:
    """Map gold-standard reference (BIP, whitepaper, RFC) parser output to NormalizedDocument."""
    pages_raw = parser_output.get("pages", [])
    blocks: List[DocumentBlock] = []

    for page_raw in pages_raw:
        page_num = page_raw.get("number", page_raw.get("page", 1))
        for block_raw in page_raw.get("blocks", []):
            blocks.append(_build_block(block_raw, page=page_num, slide=None))

    raw_meta = parser_output.get("metadata", {})
    type_meta = ReferenceMetadata(
        title=parser_output.get("title", source_filename),
        authors=raw_meta.get("authors", []),
        version=raw_meta.get("version"),
        published_date=raw_meta.get("published_date"),
        url=raw_meta.get("url"),
        bip_number=raw_meta.get("bip_number"),
        doi=raw_meta.get("doi"),
    )

    return NormalizedDocument(
        doc_id=doc_id,
        course_id=course_id,
        document_type=DocumentType.REFERENCE,
        title=parser_output.get("title", source_filename),
        source_filename=source_filename,
        parser_used=parser_used,
        parsed_at=datetime.now(),
        page_count=len(pages_raw),
        word_count=_count_words(blocks),
        blocks=blocks,
        type_metadata=type_meta.model_dump(),
        raw_metadata=raw_meta,
    )


# ---------------------------------------------------------------------------
# Dispatch entry-point
# ---------------------------------------------------------------------------

_NORMALIZERS = {
    DocumentType.LECTURE_SLIDES: normalize_lecture_slides,
    DocumentType.LECTURE_NOTES: normalize_lecture_notes,
    DocumentType.TEXTBOOK_EXCERPT: normalize_textbook_excerpt,
    DocumentType.PAST_EXAM: normalize_past_exam,
    DocumentType.REFERENCE: normalize_reference,
}


def normalize(
    document_type: DocumentType,
    parser_output: Dict[str, Any],
    doc_id: str,
    course_id: str,
    source_filename: str,
    parser_used: str,
) -> NormalizedDocument:
    """Dispatch to the appropriate normalizer and return a NormalizedDocument.

    This is the single entry-point called by the processing pipeline after
    the parser returns its raw output.
    """
    fn = _NORMALIZERS[document_type]
    return fn(
        parser_output=parser_output,
        doc_id=doc_id,
        course_id=course_id,
        source_filename=source_filename,
        parser_used=parser_used,
    )
