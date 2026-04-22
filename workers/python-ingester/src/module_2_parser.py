import uuid
import statistics
import logging
import re
from typing import List, Any
from datetime import datetime

from services.ai.app.schemas.normalized_document import (
    NormalizedDocument,
    DocumentBlock,
    BlockPosition,
    BlockType,
    DocumentType,
    TextbookExcerptMetadata
)

logger = logging.getLogger(__name__)

class StructuralParser:
    def __init__(self, course_id: str, document_id: str, document_type: DocumentType, title: str, source_filename: str):
        self.course_id = course_id
        self.document_id = document_id
        self.document_type = document_type
        self.title = title
        self.source_filename = source_filename
        self.current_section_path = []
        self.in_exclusion_zone = False # Tracks if we are in "Exercises" or "References"
        
    def _sanitize_text(self, text: str) -> str:
        # Fix PDF ligature corruption (the smoking gun from Query 20)
        text = text.replace('昀椀', 'fi').replace('昀氀', 'fl')
        # Fix squished camelCase headers (e.g., "DefiningTheLoss" -> "Defining The Loss")
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        return text

    def parse_pages(self, pages: List[Any], total_pages: int) -> NormalizedDocument:
        blocks = []
        
        # --- PPTX HANDLING (Unchanged) ---
        if self.document_type == DocumentType.LECTURE_SLIDES:
            for i, slide in enumerate(pages):
                slide_num = i + 1
                title_text = slide.shapes.title.text.strip() if slide.shapes.title else f"Slide {slide_num}"
                self.current_section_path = [self._sanitize_text(title_text)]
                
                blocks.append(DocumentBlock(
                    block_id=str(uuid.uuid4()),
                    block_type=BlockType.SLIDE_TITLE,
                    text=self.current_section_path[0],
                    position=BlockPosition(slide=slide_num, section_path=self.current_section_path.copy()),
                    heading_level=1
                ))
                
                for shape in slide.shapes:
                    if not shape.has_text_frame or shape == slide.shapes.title:
                        continue
                    body_text = self._sanitize_text(shape.text.strip())
                    if body_text:
                        blocks.append(DocumentBlock(
                            block_id=str(uuid.uuid4()),
                            block_type=BlockType.SLIDE_BODY,
                            text=body_text,
                            position=BlockPosition(slide=slide_num, section_path=self.current_section_path.copy())
                        ))
                        
        # --- PDF HANDLING (Now with Regex Armor) ---
        else:
            for page in pages:
                page_number = page.page_number
                words = page.extract_words(extra_attrs=["size"], keep_blank_chars=True)
                if not words:
                    continue

                sizes = [w['size'] for w in words if 'size' in w]
                if not sizes:
                    continue
                median_size = statistics.median(sizes)
                heading_threshold = median_size * 1.15

                lines_dict = {}
                for word in words:
                    line_y = round(word['top'] / 2) * 2
                    if line_y not in lines_dict:
                        lines_dict[line_y] = []
                    lines_dict[line_y].append(word)

                sorted_y_coords = sorted(lines_dict.keys())
                content_buffer = []

                for y_coord in sorted_y_coords:
                    line_words = lines_dict[y_coord]
                    raw_line = " ".join(w['text'] for w in line_words).strip()
                    
                    if not raw_line:
                        continue
                        
                    # 1. KILL THE TOC TRAP: Drop lines with leader dots (e.g., ".... 142")
                    if re.search(r'\.{5,}\s*\d+$', raw_line):
                        continue
                        
                    line_text = self._sanitize_text(raw_line)
                    line_size = statistics.mean([w['size'] for w in line_words])

                    # HEADING DETECTION
                    if line_size > heading_threshold and len(line_text.split()) < 15:
                        # 2. THE EXCLUSION ZONE: Check if we just hit an Exercises/References section
                        lower_head = line_text.lower()
                        if "exercises" in lower_head or "references" in lower_head or "bibliography" in lower_head:
                            self.in_exclusion_zone = True
                            content_buffer = [] # Dump whatever we had
                            continue
                        else:
                            self.in_exclusion_zone = False # Back to normal text
                            
                        if content_buffer and not self.in_exclusion_zone:
                            blocks.append(self._build_block(content_buffer, page_number))
                            content_buffer = []

                        self.current_section_path = [line_text]
                        
                        if not self.in_exclusion_zone:
                            blocks.append(DocumentBlock(
                                block_id=str(uuid.uuid4()),
                                block_type=BlockType.HEADING,
                                text=line_text,
                                position=BlockPosition(page=page_number, section_path=self.current_section_path.copy()),
                                heading_level=1
                            ))
                    else:
                        if not self.in_exclusion_zone:
                            content_buffer.append(line_text)

                if content_buffer and not self.in_exclusion_zone:
                    blocks.append(self._build_block(content_buffer, page_number))

        doc = NormalizedDocument(
            doc_id=self.document_id,
            course_id=self.course_id,
            document_type=self.document_type,
            title=self.title,
            source_filename=self.source_filename,
            parser_used="verilocal-hybrid-parser-v2",
            parsed_at=datetime.now(),
            page_count=total_pages if self.document_type != DocumentType.LECTURE_SLIDES else None,
            slide_count=total_pages if self.document_type == DocumentType.LECTURE_SLIDES else None,
            blocks=blocks,
            type_metadata=TextbookExcerptMetadata(book_title=self.title).model_dump() if self.document_type == DocumentType.TEXTBOOK_EXCERPT else None
        )
        return doc

    def _build_block(self, content_buffer: List[str], page_number: int) -> DocumentBlock:
        full_text = " ".join(content_buffer)
        return DocumentBlock(
            block_id=str(uuid.uuid4()),
            block_type=BlockType.PARAGRAPH,
            text=full_text,
            position=BlockPosition(
                page=page_number,
                section_path=self.current_section_path.copy()
            )
        )