import sys
import os

# --- MONOREPO PATH FIX ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)
services_ai_root = os.path.join(project_root, "services", "ai")
sys.path.insert(0, services_ai_root)
# -------------------------

import logging
from retrieval_3_searcher import VerilocalSearcher

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def run_cli_orchestrator(jsonl_path: str, rebuild_index: bool = False):
    searcher = VerilocalSearcher()
    
    if rebuild_index:
        logger.info("Rebuilding ChromaDB index...")
        searcher.db_manager.reset_collection()
        data_pack = searcher.embedder.process_jsonl_for_indexing(jsonl_path)
        searcher.db_manager.collection.add(
            ids=data_pack['ids'],
            embeddings=data_pack['embeddings'],
            documents=data_pack['documents'],
            metadatas=data_pack['metadatas']
        )

    print("\n" + "="*60)
    print("=== SCHEMA-COMPLIANT RAG PIPELINE ACTIVE ===")
    print("="*60)

    while True:
        try:
            query = input("\nQuery > ")
            if not query.strip():
                continue
            if query.lower() in ['exit', 'quit']:
                print("Shutting down pipeline...")
                break
            
            results = searcher.search(query=query)
            
            for i, res in enumerate(results, 1):
                # Now it uses our official Schema Labels!
                print(f"\n[Result {i}] Distance: {res['distance']:.4f} | Source: {res['label']}")
                print(f"Section: {res['section']}")
                print("-" * 40)
                print(f"Context: {res['text'][:300]}...")
        except KeyboardInterrupt:
            print("\nShutting down pipeline...")
            break

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the R-02 Retrieval CLI")
    parser.add_argument("jsonl_file", help="Path to the parsed JSONL file")
    parser.add_argument("--rebuild", action="store_true", help="Force a complete teardown and rebuild of the index")
    parser.add_argument("--index-only", action="store_true", help="Build the index and exit without starting the REPL")

    args = parser.parse_args()

    if args.index_only:
        from retrieval_2_embedder import VerilocalEmbedder
        from retrieval_1_chroma import ChromaDatabaseManager
        db = ChromaDatabaseManager()
        db.reset_collection()
        embedder = VerilocalEmbedder()
        data_pack = embedder.process_jsonl_for_indexing(args.jsonl_file)
        db.insert_batch(
            ids=data_pack["ids"],
            embeddings=data_pack["embeddings"],
            documents=data_pack["documents"],
            metadatas=data_pack["metadatas"],
        )
        logger.info(f"Index built: {db.get_collection_count()} vectors in ChromaDB.")
    else:
        run_cli_orchestrator(args.jsonl_file, rebuild_index=args.rebuild)