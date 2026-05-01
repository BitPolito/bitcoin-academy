import json
import logging
import os
import sys
from typing import Optional, Set

# --- MONOREPO PATH FIX ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)
services_ai_root = os.path.join(project_root, "services", "ai")
sys.path.insert(0, services_ai_root)
# -------------------------

from fastembed import TextEmbedding
from services.ai.app.schemas.normalized_document import DocumentChunk, ChunkType

logger = logging.getLogger(__name__)

class VerilocalEmbedder:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        index_levels: Optional[Set[ChunkType]] = None,
    ):
        # Default: index only paragraph chunks (primary retrieval unit).
        # Pass index_levels={ChunkType.MICRO} to index micro-chunks for reranking.
        self.index_levels = index_levels or {ChunkType.PARAGRAPH}
        logger.info(f"Loading embedding model: {model_name} (ONNX)")
        self.model = TextEmbedding(model_name=model_name)
        logger.info("Model loaded successfully.")

    def process_jsonl_for_indexing(self, jsonl_path: str):
        documents = []
        metadatas = []
        ids = []
        skipped = 0

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                chunk_data = json.loads(line)
                chunk = DocumentChunk(**chunk_data)

                if chunk.chunk_type not in self.index_levels:
                    skipped += 1
                    continue

                documents.append(chunk.text)
                ids.append(chunk.chunk_id)
                metadatas.append({
                    "doc_id": chunk.doc_id,
                    "course_id": chunk.course_id,
                    "lecture_id": chunk.lecture_id or chunk.doc_id,
                    "document_type": chunk.document_type.value,
                    "label": chunk.citation_label,
                    "section": chunk.citation_section or "N/A",
                    "page": chunk.citation_page or 0,
                    "slide": chunk.citation_slide or 0,
                    "chunk_type": chunk.chunk_type.value,
                    "parent_chunk_id": chunk.parent_chunk_id or "",
                    # lists serialised as comma-separated strings for Chroma compatibility
                    "tags": ",".join(chunk.tags),
                    "prerequisites": ",".join(chunk.prerequisites),
                })

        logger.info(
            f"Indexing {len(documents)} paragraph chunks "
            f"(skipped {skipped} section/micro chunks)."
        )
        embeddings = [vec.tolist() for vec in self.model.embed(documents)]

        return {
            "embeddings": embeddings,
            "documents": documents,
            "metadatas": metadatas,
            "ids": ids,
        }