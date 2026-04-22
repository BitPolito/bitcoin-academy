import os
import logging
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ChromaDatabaseManager:
    """
    R-02 Step 1: The Vector Database Manager.
    Handles local persistence of vectors, enforcing native collection teardown
    to bypass Windows OS file-locking crashes [WinError 32].
    """

    def __init__(self, persist_directory: str = "./chroma_db", collection_name: str = "bitpolito_course"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # Initialize the persistent local client
        logger.info(f"Initializing local ChromaDB at {self.persist_directory}")
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        """Creates the collection optimized for all-MiniLM-L6-v2."""
        return self.client.get_or_create_collection(
            name=self.collection_name,
            # Cosine similarity is the required distance metric for MiniLM models
            metadata={"hnsw:space": "cosine"} 
        )

    def reset_collection(self):
        """
        The Verilocal Defense: Natively drops the collection instead of using shutil.rmtree().
        Guarantees a clean slate for indexing without angering the Windows file system.
        """
        logger.info(f"Executing clean teardown of collection: {self.collection_name}")
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self._get_or_create_collection()
            logger.info("Collection successfully reset and recreated.")
        except ValueError:
            # Collection didn't exist yet, which is fine
            pass
        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            raise

    def insert_batch(self, ids: List[str], embeddings: List[List[float]], documents: List[str], metadatas: List[Dict[str, Any]]):
        """
        Inserts a precise batch of vectors into the database.
        """
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.debug(f"Safely inserted batch of {len(ids)} vectors into ChromaDB.")
        except Exception as e:
            logger.error(f"Failed to insert batch into ChromaDB: {e}")
            raise
            
    def get_collection_count(self) -> int:
        """Returns the total number of vectors currently indexed."""
        return self.collection.count()