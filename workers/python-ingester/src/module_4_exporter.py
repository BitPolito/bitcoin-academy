import os
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class JsonlExporter:
    """
    Module 4: Metadata Sanitizer & Contingency Exporter.
    Enforces strict typing for ChromaDB and writes chunks line-by-line to SSD
    to survive unexpected OS crashes.
    """

    def __init__(self, output_dir: str = "./output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def sanitize_and_export(self, chunks: List[Dict[str, Any]], document_id: str) -> str:
        """
        Sanitizes chunk metadata and appends them to a JSONL file.
        """
        output_file = os.path.join(self.output_dir, f"{document_id}_contingency.jsonl")
        
        # Open in append mode ('a') for crash survival
        with open(output_file, 'a', encoding='utf-8') as f:
            for chunk in chunks:
                # ChromaDB strictly requires strings, ints, floats, or bools in metadata.
                # No nested dicts, lists, or NoneTypes allowed.
                
                sanitized_chunk = {
                    "chunk_id": str(chunk.get("chunk_id", "")),
                    # Convert null parents to a strict string to avoid ChromaDB rejection
                    "parent_id": str(chunk.get("parent_id")) if chunk.get("parent_id") != "null" else "NONE",
                    "course_id": str(chunk.get("course_id", "unknown")),
                    "document_id": str(chunk.get("document_id", document_id)),
                    "type": str(chunk.get("type", "UNKNOWN")),
                    "text": str(chunk.get("text", "")),
                    # Positional Metadata
                    "section_title": str(chunk.get("section_title", "Document Start")),
                    "page_str": str(chunk.get("page_str", "0")),
                    "priority": int(chunk.get("priority", 0))
                }
                
                # Write immediately to SSD
                f.write(json.dumps(sanitized_chunk) + '\n')
                
        logger.debug(f"Safely appended {len(chunks)} chunks to {output_file}")
        return output_file
    
    