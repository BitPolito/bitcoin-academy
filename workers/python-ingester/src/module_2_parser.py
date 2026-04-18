import uuid
import statistics
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class StructuralParser:
    def __init__(self, course_id: str, document_id: str):
        self.course_id = course_id
        self.document_id = document_id
        self.current_section_id = None
        self.current_section_title = "Document Start"
        
    def parse_pages(self, pages: List[Any]) -> List[Dict[str, Any]]:
        extracted_chunks = []
        
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
                line_text = " ".join(w['text'] for w in line_words).strip()
                if not line_text:
                    continue
                    
                line_size = statistics.mean([w['size'] for w in line_words])

                if line_size > heading_threshold and len(line_text.split()) < 15:
                    if content_buffer:
                        extracted_chunks.append(self._build_content_chunk(content_buffer, page_number))
                        content_buffer = []

                    self.current_section_id = str(uuid.uuid4())
                    self.current_section_title = line_text
                    
                    extracted_chunks.append({
                        "chunk_id": self.current_section_id,
                        "parent_id": "null",
                        "course_id": self.course_id,
                        "document_id": self.document_id,
                        "type": "SECTION",
                        "text": self.current_section_title,
                        "section_title": self.current_section_title,
                        "page_str": str(page_number),
                        "priority": 0
                    })
                else:
                    content_buffer.append(line_text)

            if content_buffer:
                extracted_chunks.append(self._build_content_chunk(content_buffer, page_number))

        return extracted_chunks

    def _build_content_chunk(self, content_buffer: List[str], page_number: int) -> Dict[str, Any]:
        if not self.current_section_id:
            self.current_section_id = str(uuid.uuid4())
        full_text = " ".join(content_buffer)
        return {
            "chunk_id": str(uuid.uuid4()),
            "parent_id": self.current_section_id,
            "course_id": self.course_id,
            "document_id": self.document_id,
            "type": "CONTENT",
            "text": full_text,
            "section_title": self.current_section_title,
            "page_str": str(page_number),
            "priority": 1
        }