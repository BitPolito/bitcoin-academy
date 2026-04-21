import json
import logging
import os
import sys

# --- MONOREPO PATH FIX ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)
services_ai_root = os.path.join(project_root, "services", "ai")
sys.path.insert(0, services_ai_root)
# -------------------------

from fastembed import TextEmbedding
from services.ai.app.schemas.normalized_document import DocumentChunk

logger = logging.getLogger(__name__)

class VerilocalEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        logger.info(f"Loading embedding model: {model_name} (ONNX)")
        self.model = TextEmbedding(model_name=model_name)
        logger.info("Model loaded successfully.")

    def process_jsonl_for_indexing(self, jsonl_path: str):
        documents = []
        metadatas = []
        ids = []

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Load the line into a formal DocumentChunk object
                chunk_data = json.loads(line)
                chunk = DocumentChunk(**chunk_data)

                documents.append(chunk.text)
                ids.append(chunk.chunk_id)
                
                # Store official citation metadata for the UI
                metadatas.append({
                    "doc_id": chunk.doc_id,
                    "course_id": chunk.course_id,
                    "label": chunk.citation_label,
                    "section": chunk.citation_section or "N/A",
                    "page": chunk.citation_page or 0
                })

        logger.info(f"Generating vectors for {len(documents)} chunks...")
        # Convert the NumPy arrays to native Python lists of floats
        embeddings = [vec.tolist() for vec in self.model.embed(documents)]
        
        return {
            "embeddings": embeddings,
            "documents": documents,
            "metadatas": metadatas,
            "ids": ids
        }