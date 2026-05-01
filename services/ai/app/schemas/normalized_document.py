"""Normalized academic document schema.

This is the canonical internal representation for all course materials after
parsing and before chunking.  Every document type (slides, notes, textbooks,
exams, reference documents) is reduced to this common format so that the
chunking and retrieval layers can work uniformly.

Pipeline position:
    raw file  →  parser  →  NormalizedDocument  →  DocumentChunk[]  →  vector index
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DocumentType(str, Enum):
    """Academic source types supported by the ingestion pipeline."""

    LECTURE_SLIDES = "lecture_slides"
    LECTURE_NOTES = "lecture_notes"
    TEXTBOOK_EXCERPT = "textbook_excerpt"
    PAST_EXAM = "past_exam"
    REFERENCE = "reference"


class ChunkType(str, Enum):
    """Hierarchical granularity level of a DocumentChunk.

    SECTION   — Level 1: all blocks under one heading; broadest context unit.
    PARAGRAPH — Level 2: primary retrieval unit (~1500 chars), grouped by topic.
    MICRO     — Level 3: sentence-boundary sub-split (~300 chars), for reranking.
    """

    SECTION = "section"
    PARAGRAPH = "paragraph"
    MICRO = "micro"


class BlockType(str, Enum):
    """Atomic content unit types.

    Universal types work across all document types.
    Type-specific variants (SLIDE_*, EXAM_*) carry additional semantics used
    by the chunker and the citation formatter.
    """

    # Universal
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    CODE_BLOCK = "code_block"
    MATH = "math"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"
    PAGE_BREAK = "page_break"

    # Slides-specific
    SLIDE_TITLE = "slide_title"
    SLIDE_BODY = "slide_body"
    SPEAKER_NOTES = "speaker_notes"

    # Exam-specific
    EXAM_QUESTION = "exam_question"
    EXAM_ANSWER = "exam_answer"
    EXAM_SECTION = "exam_section"


# ---------------------------------------------------------------------------
# Block position — source location used for citations
# ---------------------------------------------------------------------------


class BlockPosition(BaseModel):
    """Where in the source document a block originates.

    All fields are optional so the same model works for every document type.
    Consumers should check ``document_type`` to know which fields are
    meaningful.
    """

    page: Optional[int] = Field(None, description="1-indexed page number")
    slide: Optional[int] = Field(None, description="1-indexed slide number")
    section_path: List[str] = Field(
        default_factory=list,
        description=(
            "Breadcrumb of enclosing headings, outermost first.  "
            "Example: ['Chapter 3 — Keys', '3.1 Private Keys']"
        ),
    )
    paragraph_index: Optional[int] = Field(
        None, description="0-indexed position of this block within its page/slide"
    )


# ---------------------------------------------------------------------------
# DocumentBlock — atomic unit of content
# ---------------------------------------------------------------------------


class DocumentBlock(BaseModel):
    """One atomic content unit extracted from a source document.

    The ``text`` field is always populated and always contains plain text so
    that it can be directly embedded or searched without further processing.
    Type-specific fields (heading_level, language, …) are set only when
    relevant to the block type.
    """

    block_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable identifier for this block within the document",
    )
    block_type: BlockType
    text: str = Field(description="Plain-text content of this block")
    position: BlockPosition

    # HEADING
    heading_level: Optional[int] = Field(
        None,
        ge=1,
        le=6,
        description="Heading depth (1 = top-level) for HEADING blocks",
    )

    # CODE_BLOCK
    language: Optional[str] = Field(
        None, description="Programming language hint for syntax highlighting"
    )

    # EXAM_QUESTION
    question_number: Optional[str] = Field(
        None, description="Label from the exam paper, e.g. '2a' or 'Q3'"
    )
    marks: Optional[int] = Field(
        None, description="Point value of the question"
    )

    # TABLE (markdown-serialized for plain-text fallback)
    table_markdown: Optional[str] = Field(
        None, description="Full table content in Markdown for display purposes"
    )


# ---------------------------------------------------------------------------
# Source-type metadata — additional context per document type
# ---------------------------------------------------------------------------


class LectureSlidesMetadata(BaseModel):
    """Metadata specific to lecture slide decks."""

    course_name: Optional[str] = None
    lecture_number: Optional[int] = None
    total_slides: Optional[int] = None


class LectureNotesMetadata(BaseModel):
    """Metadata specific to written lecture notes."""

    course_name: Optional[str] = None
    lecture_number: Optional[int] = None
    topics: List[str] = Field(default_factory=list)


class TextbookExcerptMetadata(BaseModel):
    """Metadata specific to textbook excerpts."""

    book_title: str
    authors: List[str] = Field(default_factory=list)
    edition: Optional[str] = None
    chapter: Optional[str] = None
    isbn: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None


class PastExamMetadata(BaseModel):
    """Metadata specific to past examination papers."""

    course_name: Optional[str] = None
    exam_date: Optional[str] = None
    academic_year: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_marks: Optional[int] = None
    with_solutions: bool = False


class ReferenceMetadata(BaseModel):
    """Metadata specific to gold-standard reference documents (BIPs, whitepapers, RFCs …)."""

    title: str
    authors: List[str] = Field(default_factory=list)
    version: Optional[str] = None
    published_date: Optional[str] = None
    url: Optional[str] = None
    bip_number: Optional[int] = Field(
        None, description="Bitcoin Improvement Proposal number if applicable"
    )
    doi: Optional[str] = None


# Union used for type-narrowing in services that need typed access
DocumentTypeMetadata = Union[
    LectureSlidesMetadata,
    LectureNotesMetadata,
    TextbookExcerptMetadata,
    PastExamMetadata,
    ReferenceMetadata,
]


# ---------------------------------------------------------------------------
# NormalizedDocument — canonical post-parse representation
# ---------------------------------------------------------------------------


class NormalizedDocument(BaseModel):
    """Canonical internal representation of a course document after parsing.

    A NormalizedDocument is produced by the parsing/normalization stage and
    consumed by the chunking stage.  It is stored as JSON in
    ``CourseDocument.sections_json`` (and optionally in an object store for
    large documents) so that chunking can be re-run without re-parsing.

    Design constraints:
    - ``blocks`` is a flat ordered list; hierarchy is encoded in
      ``BlockPosition.section_path`` and ``heading_level``.
    - Every block's ``text`` is plain UTF-8 — no HTML, no LaTeX.
    - All fields needed for citation rendering are present on each block.
    """

    doc_id: str = Field(description="Matches CourseDocument.id")
    course_id: str
    document_type: DocumentType
    title: str
    language: str = Field(default="en", description="BCP-47 language code")
    source_filename: str
    parser_used: str = Field(
        description="Identifier of the parser that produced this document, e.g. 'pymupdf-1.24'"
    )
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))

    page_count: Optional[int] = None
    slide_count: Optional[int] = None
    word_count: Optional[int] = None

    # --- Document-level classification metadata ----------------------------
    lecture_id: Optional[str] = Field(
        None,
        description="Lecture/document identifier within the course (e.g. 'L03', 'BIP141')",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Topic tags for content filtering (e.g. ['cryptography', 'hashing'])",
    )
    prerequisites: List[str] = Field(
        default_factory=list,
        description="Prerequisite topic labels (e.g. ['public-key-crypto', 'hash-functions'])",
    )

    blocks: List[DocumentBlock] = Field(
        default_factory=list,
        description="Ordered list of content blocks extracted from the source",
    )

    # Typed metadata per document type — serialised to dict for storage
    type_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Source-type-specific metadata as a plain dict.  "
            "Cast to the appropriate *Metadata model using ``document_type``."
        ),
    )

    # Passthrough of any extra fields returned by the parser
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)

    # -----------------------------------------------------------------------
    # Convenience helpers
    # -----------------------------------------------------------------------

    def typed_metadata(self) -> Optional[DocumentTypeMetadata]:
        """Return ``type_metadata`` cast to the correct typed model."""
        if self.type_metadata is None:
            return None
        mapping: Dict[DocumentType, Any] = {
            DocumentType.LECTURE_SLIDES: LectureSlidesMetadata,
            DocumentType.LECTURE_NOTES: LectureNotesMetadata,
            DocumentType.TEXTBOOK_EXCERPT: TextbookExcerptMetadata,
            DocumentType.PAST_EXAM: PastExamMetadata,
            DocumentType.REFERENCE: ReferenceMetadata,
        }
        cls = mapping.get(self.document_type)
        return cls(**self.type_metadata) if cls else None

    def blocks_for_page(self, page: int) -> List[DocumentBlock]:
        return [b for b in self.blocks if b.position.page == page]

    def blocks_for_slide(self, slide: int) -> List[DocumentBlock]:
        return [b for b in self.blocks if b.position.slide == slide]

    def heading_blocks(self) -> List[DocumentBlock]:
        return [b for b in self.blocks if b.block_type == BlockType.HEADING]


# ---------------------------------------------------------------------------
# DocumentChunk — output of the chunking stage, input to the vector index
# ---------------------------------------------------------------------------


class DocumentChunk(BaseModel):
    """One retrievable unit produced by splitting a NormalizedDocument.

    Each chunk is self-contained: it carries enough metadata to render a
    citation without looking up the parent document.

    Chunks are stored in the vector index (e.g. pgvector or Chroma) and
    returned by the RAG retriever.
    """

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str
    course_id: str
    lecture_id: Optional[str] = Field(
        None, description="Lecture/document ID within the course"
    )
    document_type: DocumentType

    text: str = Field(description="The text to embed and return in retrieval")
    block_ids: List[str] = Field(
        description="IDs of the source DocumentBlocks this chunk spans"
    )

    # --- Classification metadata (inherited from NormalizedDocument) --------
    tags: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)

    # --- Citation fields (always populated) --------------------------------
    citation_page: Optional[int] = Field(
        None, description="Page number of the first block in this chunk"
    )
    citation_slide: Optional[int] = Field(
        None, description="Slide number of the first block in this chunk"
    )
    citation_section: Optional[str] = Field(
        None,
        description=(
            "Innermost enclosing section heading, e.g. '3.2 Hash Functions'.  "
            "Derived from the last element of the first block's section_path."
        ),
    )
    citation_label: str = Field(
        description=(
            "Human-readable location string shown in the UI, "
            "e.g. 'Slide 12', 'p. 45', 'Q3', 'Section 2.1'"
        )
    )

    chunk_index: int = Field(description="0-indexed position of this chunk within its document")
    char_count: int

    # --- Hierarchy fields (R-01) -------------------------------------------
    chunk_type: ChunkType = Field(
        default=ChunkType.PARAGRAPH,
        description="Granularity level: section (L1), paragraph (L2), micro (L3)",
    )
    parent_chunk_id: Optional[str] = Field(
        None,
        description=(
            "chunk_id of the parent in the hierarchy.  "
            "None for section chunks; section chunk_id for paragraph chunks; "
            "paragraph chunk_id for micro chunks."
        ),
    )

    # -----------------------------------------------------------------------
    # Factory
    # -----------------------------------------------------------------------

    @classmethod
    def from_blocks(
        cls,
        blocks: List[DocumentBlock],
        doc: NormalizedDocument,
        chunk_index: int,
        chunk_type: Optional["ChunkType"] = None,
        parent_chunk_id: Optional[str] = None,
    ) -> "DocumentChunk":
        """Build a chunk from a contiguous list of DocumentBlocks."""
        if not blocks:
            raise ValueError("Cannot create a chunk from an empty block list")

        if chunk_type is None:
            chunk_type = ChunkType.PARAGRAPH

        text = "\n\n".join(b.text for b in blocks)
        first = blocks[0].position
        section = first.section_path[-1] if first.section_path else None

        if first.slide is not None:
            label = f"Slide {first.slide}"
        elif first.page is not None:
            label = f"p. {first.page}"
        elif section:
            label = section
        else:
            label = f"chunk {chunk_index + 1}"

        return cls(
            doc_id=doc.doc_id,
            course_id=doc.course_id,
            lecture_id=doc.lecture_id,
            document_type=doc.document_type,
            text=text,
            block_ids=[b.block_id for b in blocks],
            citation_page=first.page,
            citation_slide=first.slide,
            citation_section=section,
            citation_label=label,
            chunk_index=chunk_index,
            char_count=len(text),
            chunk_type=chunk_type,
            parent_chunk_id=parent_chunk_id,
            tags=list(doc.tags),
            prerequisites=list(doc.prerequisites),
        )
