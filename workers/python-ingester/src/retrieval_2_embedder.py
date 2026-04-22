import json
import logging
from typing import List, Dict, Any

# We import TextEmbedding from fastembed (which uses ONNX under the hood)
from fastembed import TextEmbedding 

logger = logging.getLogger(__name__)

class VerilocalEmbedder:
    """
    R-02 Step 2: The FastEmbed Batching Engine.
    Reads R-01 JSONL output, vectorizes strictly the MICRO chunks, 
    and enforces memory safety via 250-chunk batching and native float casting.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", batch_size: int = 250):
        self.batch_size = batch_size
        logger.info(f"Loading embedding model: {model_name} (ONNX)")
        
        # fastembed automatically downloads and caches the model locally on first run
        self.model = TextEmbedding(model_name=model_name)
        logger.info("Model loaded successfully into memory.")

    def embed_and_store(self, jsonl_path: str, db_manager: Any):
        """
        Reads the contingency log line-by-line to prevent loading massive files into RAM.
        Filters for MICRO chunks, batches them, and pushes to ChromaDB.
        """
        logger.info(f"Starting embedding process for {jsonl_path}")
        
        batch_ids = []
        batch_texts = []
        batch_metadatas = []
        
        processed_count = 0
        
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                chunk = json.loads(line)
                
                # Verilocal Defense: Only embed MICRO chunks.
                # Embedding full paragraphs dilutes accuracy.
                if chunk.get("type") != "MICRO":
                    continue
                    
                batch_ids.append(chunk["chunk_id"])
                batch_texts.append(chunk["text"])
                batch_metadatas.append(chunk)
                
                # When buffer hits the strict 250 limit
                if len(batch_texts) >= self.batch_size:
                    self._process_batch(batch_ids, batch_texts, batch_metadatas, db_manager)
                    processed_count += len(batch_texts)
                    
                    # Clear RAM buffers
                    batch_ids, batch_texts, batch_metadatas = [], [], []
                    
        # Flush any remaining chunks at the end of the file
        if batch_texts:
            self._process_batch(batch_ids, batch_texts, batch_metadatas, db_manager)
            processed_count += len(batch_texts)
            
        logger.info(f"Embedding complete. {processed_count} highly targeted MICRO chunks indexed.")

    def _process_batch(self, ids: List[str], texts: List[str], metadatas: List[Dict[str, Any]], db_manager: Any):
        """Vectorizes a batch and enforces ChromaDB type safety."""
        logger.debug(f"Vectorizing batch of {len(texts)} chunks...")
        
        # fastembed returns an iterable generator of numpy arrays
        embeddings_gen = self.model.embed(texts)
        
        # Verilocal Defense: ChromaDB strict typing. Force .tolist()
        # If this is skipped, ChromaDB throws an opaque validation error and crashes.
        embeddings_list = [vec.tolist() for vec in embeddings_gen]
        
        # Hand off to Module 1 to physically write to SSD
        db_manager.insert_batch(
            ids=ids,
            embeddings=embeddings_list,
            documents=texts,
            metadatas=metadatas
        )