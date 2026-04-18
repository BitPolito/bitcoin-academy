import json
import logging
from typing import List, Dict, Any
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

class HierarchicalSearcher:
    """
    R-02 Step 3: The Hierarchical Searcher.
    Embeds user queries, finds high-precision MICRO chunks, and executes
    the Parent-Fetch to return full CONTENT blocks for LLM reasoning.
    """

    def __init__(self, db_manager: Any, jsonl_path: str, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.db_manager = db_manager
        
        logger.info("Initializing search embedder...")
        self.model = TextEmbedding(model_name=model_name)
        
        # Build the lightweight RAM dictionary for Parent-Fetch lookups
        self.context_lookup = self._build_context_lookup(jsonl_path)

    def _build_context_lookup(self, jsonl_path: str) -> Dict[str, Dict[str, Any]]:
        """
        Loads only SECTION and CONTENT chunks into a lightweight memory dictionary.
        This allows O(1) instantaneous lookups for the Parent-Fetch without heavy DB loads.
        """
        logger.info(f"Building in-memory Context Lookup from {jsonl_path}...")
        lookup = {}
        
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                chunk = json.loads(line)
                # We do not need MICRO chunks in the lookup table, they are in Chroma
                if chunk.get("type") in ["SECTION", "CONTENT"]:
                    lookup[chunk["chunk_id"]] = chunk
                    
        logger.info(f"Context Lookup ready. {len(lookup)} structural blocks loaded into RAM.")
        return lookup

    def search(self, query: str, top_k_micro: int = 5) -> List[Dict[str, Any]]:
        """
        Executes the Hierarchical Retrieval.
        """
        logger.debug(f"Executing search for query: '{query}'")
        
        # 1. Embed the user's query
        query_embedding_gen = self.model.embed([query])
        query_vector = list(query_embedding_gen)[0].tolist()

        # 2. Search ChromaDB for the Top-K MICRO chunks
        results = self.db_manager.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k_micro,
            include=["metadatas", "distances"]
        )

        if not results['metadatas'] or not results['metadatas'][0]:
            logger.warning("No matches found in ChromaDB.")
            return []

        # 3. Extract and Deduplicate Parent IDs
        retrieved_metadatas = results['metadatas'][0]
        distances = results['distances'][0]
        
        evidence_pack = []
        seen_parent_ids = set()

        for meta, distance in zip(retrieved_metadatas, distances):
            parent_id = meta.get("parent_id")
            
            # Defensive check: Ensure we don't process the same paragraph twice
            if parent_id and parent_id != "NONE" and parent_id not in seen_parent_ids:
                seen_parent_ids.add(parent_id)
                
                # 4. The Parent-Fetch: Grab the full paragraph/slide from RAM
                parent_chunk = self.context_lookup.get(parent_id)
                
                if parent_chunk:
                    evidence_pack.append({
                        "distance": distance, # Lower distance = better match (Cosine)
                        "section_title": parent_chunk.get("section_title"),
                        "page_str": parent_chunk.get("page_str"),
                        "full_text": parent_chunk.get("text"),
                        "micro_hit": meta.get("text") # Keeping the exact sentence that triggered the match for debugging
                    })

        logger.info(f"Retrieved {len(evidence_pack)} unique CONTENT blocks for the Evidence Pack.")
        return evidence_pack