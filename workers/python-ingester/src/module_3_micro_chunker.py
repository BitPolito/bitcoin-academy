import logging
from typing import List
from services.ai.app.schemas.normalized_document import NormalizedDocument, DocumentChunk, DocumentBlock

logger = logging.getLogger(__name__)

class VerilocalChunker:
    def __init__(self, max_char_limit: int = 1500):
        self.max_char_limit = max_char_limit

    def process_document(self, doc: NormalizedDocument) -> List[DocumentChunk]:
        chunks = []
        current_group: List[DocumentBlock] = []
        current_len = 0
        chunk_idx = 0

        for block in doc.blocks:
            if not block.text.strip():
                continue
                
            block_len = len(block.text)
            
            # If adding this block exceeds the limit, flush the current group into a DocumentChunk
            if current_len + block_len > self.max_char_limit and current_group:
                chunks.append(DocumentChunk.from_blocks(current_group, doc, chunk_idx))
                chunk_idx += 1
                current_group = []
                current_len = 0
                
            current_group.append(block)
            current_len += block_len

        # Flush any remaining blocks in the final group
        if current_group:
            chunks.append(DocumentChunk.from_blocks(current_group, doc, chunk_idx))

        logger.info(f"Chunking complete. Produced {len(chunks)} official DocumentChunks.")
        return chunks