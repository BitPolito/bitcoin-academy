import uuid
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class VerilocalMicroChunker:
    def __init__(self, max_char_limit: int = 8000, chunk_size: int = 500, overlap: int = 50):
        self.max_char_limit = max_char_limit
        self.chunk_size = chunk_size
        self.overlap = overlap

    def process_chunks(self, structural_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        final_chunks = []
        for chunk in structural_chunks:
            if chunk["type"] == "SECTION":
                final_chunks.append(chunk)
                continue
            
            if chunk["type"] == "CONTENT":
                text = chunk["text"]
                if len(text) > self.max_char_limit:
                    logger.warning(f"Guillotine activated on {chunk['chunk_id']}.")
                    text = text[:self.max_char_limit]
                    chunk["text"] = text
                
                final_chunks.append(chunk)

                micro_texts = self._chunk_text_with_overlap(text)
                for micro_text in micro_texts:
                    if len(micro_text.strip()) < 10:
                        continue
                    final_chunks.append({
                        "chunk_id": str(uuid.uuid4()),
                        "parent_id": chunk["chunk_id"],
                        "course_id": chunk["course_id"],
                        "document_id": chunk["document_id"],
                        "type": "MICRO",
                        "text": micro_text,
                        "section_title": chunk.get("section_title"),
                        "page_str": chunk.get("page_str"),
                        "priority": 2
                    })
        return final_chunks

    def _chunk_text_with_overlap(self, text: str) -> List[str]:
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + self.chunk_size
            if end < text_len:
                last_space = text.rfind(' ', start, end)
                if last_space != -1 and last_space > start:
                    end = last_space
                    
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)
                
            start = end - self.overlap
            if start < text_len and start > 0 and text[start - 1] != ' ':
                next_space = text.find(' ', start)
                if next_space != -1:
                    start = next_space + 1
                else:
                    break
        return chunks