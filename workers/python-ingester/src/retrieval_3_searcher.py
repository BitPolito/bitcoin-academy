import os
import logging
from retrieval_1_chroma import ChromaDatabaseManager
from retrieval_2_embedder import VerilocalEmbedder

# Silence ChromaDB telemetry bug
os.environ["CHROMA_TELEMETRY_IMPL"] = "INMEMORY"

logger = logging.getLogger(__name__)

class VerilocalSearcher:
    def __init__(self):
        self.db_manager = ChromaDatabaseManager()
        self.embedder = VerilocalEmbedder()

    def _sanitize_query(self, text: str) -> str:
        # Give the search bar the same armor as the parser
        return text.replace('昀椀', 'fi').replace('昀氀', 'fl')

    def search(self, query: str, top_k: int = 3):
        # 1. Clean the incoming user query!
        clean_query = self._sanitize_query(query)
        
        # 2. Embed the clean query
        query_vector = list(self.embedder.model.embed([clean_query]))[0]
        
        # Query Chroma
        results = self.db_manager.collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=top_k
        )

        formatted_results = []
        for i in range(len(results['ids'][0])):
            formatted_results.append({
                "id": results['ids'][0][i],
                "text": results['documents'][0][i],
                "distance": results['distances'][0][i],
                "label": results['metadatas'][0][i]['label'],
                "section": results['metadatas'][0][i]['section']
            })
        
        return formatted_results