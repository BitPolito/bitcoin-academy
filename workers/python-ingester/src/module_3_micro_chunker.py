import uuid
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class VerilocalMicroChunker:
    """
    Module 3: The 'Verilocal' Micro-Chunker.
    Enforces hardware safety (The Guillotine) and RAG optimization (Overlapping Windows).
    Transforms Level 2 (CONTENT) chunks into embeddable Level 3 (MICRO) chunks.
    """

    def __init__(self, max_char_limit: int = 8000, chunk_size: int = 500, overlap: int = 50):
        self.max_char_limit = max_char_limit
        self.chunk_size = chunk_size
        self.overlap = overlap

    def process_chunks(self, structural_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Receives structural chunks from Module 2 and expands them with MICRO chunks.
        """
        final_chunks = []
        
        for chunk in structural_chunks:
            # SECTION chunks pass through untouched
            if chunk["type"] == "SECTION":
                final_chunks.append(chunk)
                continue
            
            if chunk["type"] == "CONTENT":
                text = chunk["text"]
                
                # 1. The Guillotine: Prevent ONNX Segfaults
                if len(text) > self.max_char_limit:
                    logger.warning(f"Guillotine activated on chunk {chunk['chunk_id']}. Truncating {len(text)} chars to {self.max_char_limit}.")
                    text = text[:self.max_char_limit]
                    chunk["text"] = text  # Update the parent content chunk text as well
                
                # Add the sanitized CONTENT chunk to the final list
                final_chunks.append(chunk)

                # 2. Sliding Window: Generate MICRO chunks for Dense Retrieval
                micro_texts = self._chunk_text_with_overlap(text)
                
                for micro_text in micro_texts:
                    if len(micro_text.strip()) < 10:
                        continue  # Skip uselessly small fragments
                        
                    final_chunks.append({
                        "chunk_id": str(uuid.uuid4()),
                        "parent_id": chunk["chunk_id"],  # Link strictly to the CONTENT chunk
                        "course_id": chunk["course_id"],
                        "document_id": chunk["document_id"],
                        "type": "MICRO",
                        "text": micro_text,
                        "section_title": chunk.get("section_title"),
                        "page_str": chunk.get("page_str"),
                        "priority": 2  # Highest priority for embedding engine
                    })

        return final_chunks

    def _chunk_text_with_overlap(self, text: str) -> List[str]:
        """
        Splits text into chunks of `self.chunk_size` characters with `self.overlap` characters overlapping.
        Snaps to the nearest space to avoid cutting words in half.
        """
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + self.chunk_size
            
            # Snap 'end' to the nearest previous space to preserve word boundaries
            if end < text_len:
                last_space = text.rfind(' ', start, end)
                if last_space != -1 and last_space > start:
                    end = last_space
                    
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)
                
            # Advance the start pointer, stepping back by the overlap amount
            start = end - self.overlap
            
            # Snap 'start' to the next space to avoid starting a chunk mid-word
            if start < text_len and start > 0 and text[start - 1] != ' ':
                next_space = text.find(' ', start)
                if next_space != -1:
                    start = next_space + 1
                else:
                    break  # Reached the absolute end of the string
                    
        return chunks