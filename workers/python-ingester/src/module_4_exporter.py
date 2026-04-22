import os
import logging
from typing import List
from services.ai.app.schemas.normalized_document import DocumentChunk

logger = logging.getLogger(__name__)

class JsonlExporter:
    def __init__(self, output_dir: str = "./parsed_output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_chunks(self, chunks: List[DocumentChunk], document_id: str) -> str:
        output_file = os.path.join(self.output_dir, f"{document_id}_contingency.jsonl")
        
        
        with open(output_file, 'a', encoding='utf-8') as f:
            for chunk in chunks:
                f.write(chunk.model_dump_json() + '\n')
                
        logger.info(f"Safely exported {len(chunks)} DocumentChunks to {output_file}")
        return output_file