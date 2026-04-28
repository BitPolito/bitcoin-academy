import re
import logging
from typing import List

from services.ai.app.schemas.normalized_document import (
    NormalizedDocument, DocumentChunk, DocumentBlock, BlockType, ChunkType
)

logger = logging.getLogger(__name__)


class Chunker:
    """Three-level hierarchical chunker (R-01).

    Level 1 — SECTION   : all blocks under one heading boundary (~unbounded size).
    Level 2 — PARAGRAPH : groups of blocks up to max_char_limit (~1500 chars).
    Level 3 — MICRO     : sentence-boundary splits of each paragraph (~300 chars).

    Only PARAGRAPH chunks are indexed in the vector store by default; SECTION
    and MICRO chunks are stored in JSONL for context expansion and reranking.
    """

    BOUNDARY_TYPES = {BlockType.HEADING, BlockType.SLIDE_TITLE}

    def __init__(self, max_char_limit: int = 1500, micro_char_limit: int = 300):
        self.max_char_limit = max_char_limit
        self.micro_char_limit = micro_char_limit

    def process_document(self, doc: NormalizedDocument) -> List[DocumentChunk]:
        if not doc.blocks:
            return []

        all_chunks: List[DocumentChunk] = []
        chunk_idx = 0

        for section_blocks in self._split_into_sections(doc.blocks):
            # L1 — section chunk
            sec_chunk = DocumentChunk.from_blocks(
                section_blocks, doc, chunk_idx,
                chunk_type=ChunkType.SECTION,
            )
            all_chunks.append(sec_chunk)
            chunk_idx += 1

            for para_blocks in self._split_into_paragraphs(section_blocks):
                # L2 — paragraph chunk
                para_chunk = DocumentChunk.from_blocks(
                    para_blocks, doc, chunk_idx,
                    chunk_type=ChunkType.PARAGRAPH,
                    parent_chunk_id=sec_chunk.chunk_id,
                )
                all_chunks.append(para_chunk)
                chunk_idx += 1

                # L3 — micro chunks
                for micro_text in self._split_into_micros(para_chunk.text):
                    all_chunks.append(DocumentChunk(
                        doc_id=doc.doc_id,
                        course_id=doc.course_id,
                        document_type=doc.document_type,
                        text=micro_text,
                        block_ids=para_chunk.block_ids,
                        citation_page=para_chunk.citation_page,
                        citation_slide=para_chunk.citation_slide,
                        citation_section=para_chunk.citation_section,
                        citation_label=para_chunk.citation_label,
                        chunk_index=chunk_idx,
                        char_count=len(micro_text),
                        chunk_type=ChunkType.MICRO,
                        parent_chunk_id=para_chunk.chunk_id,
                    ))
                    chunk_idx += 1

        n_sec = sum(1 for c in all_chunks if c.chunk_type == ChunkType.SECTION)
        n_par = sum(1 for c in all_chunks if c.chunk_type == ChunkType.PARAGRAPH)
        n_mic = sum(1 for c in all_chunks if c.chunk_type == ChunkType.MICRO)
        logger.info(
            f"Chunking complete: {n_sec} section | {n_par} paragraph | {n_mic} micro "
            f"= {len(all_chunks)} total chunks."
        )
        return all_chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _split_into_sections(self, blocks: List[DocumentBlock]) -> List[List[DocumentBlock]]:
        """Group blocks into sections, splitting at heading/slide-title boundaries."""
        sections: List[List[DocumentBlock]] = []
        current: List[DocumentBlock] = []

        for block in blocks:
            if block.block_type in self.BOUNDARY_TYPES and current:
                sections.append(current)
                current = []
            current.append(block)

        if current:
            sections.append(current)

        return sections or [blocks]

    def _split_into_paragraphs(self, blocks: List[DocumentBlock]) -> List[List[DocumentBlock]]:
        """Group blocks into paragraph-sized chunks (up to max_char_limit chars)."""
        groups: List[List[DocumentBlock]] = []
        current: List[DocumentBlock] = []
        current_len = 0

        for block in blocks:
            text = block.text.strip()
            if not text:
                continue
            blen = len(text)
            if current_len + blen > self.max_char_limit and current:
                groups.append(current)
                current = []
                current_len = 0
            current.append(block)
            current_len += blen

        if current:
            groups.append(current)

        return groups

    def _split_into_micros(self, text: str) -> List[str]:
        """Split text into micro-chunks at sentence boundaries."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        micros: List[str] = []
        current: List[str] = []
        current_len = 0

        for sent in sentences:
            if current_len + len(sent) > self.micro_char_limit and current:
                micros.append(" ".join(current))
                current = []
                current_len = 0
            current.append(sent)
            current_len += len(sent)

        if current:
            micros.append(" ".join(current))

        return micros or [text]
