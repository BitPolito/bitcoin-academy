import os
import sys
import logging
from retrieval_1_chroma import ChromaDatabaseManager
from retrieval_2_embedder import VerilocalEmbedder
from retrieval_3_searcher import HierarchicalSearcher

# Configure terminal logging to only show critical info so it doesn't drown out the search results
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_cli_orchestrator(jsonl_path: str, rebuild_index: bool = False):
    if not os.path.exists(jsonl_path):
        logger.error(f"Cannot find data file at {jsonl_path}. Run R-01 first.")
        sys.exit(1)

    # 1. Initialize the Database
    db_manager = ChromaDatabaseManager(persist_directory="./chroma_db", collection_name="bitpolito_course")
    
    if rebuild_index:
        db_manager.reset_collection()

    # 2. Build Index if empty
    if db_manager.get_collection_count() == 0:
        logger.info("ChromaDB index is empty. Commencing Verilocal embedding phase...")
        embedder = VerilocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2", batch_size=250)
        embedder.embed_and_store(jsonl_path=jsonl_path, db_manager=db_manager)
    else:
        logger.info(f"Database already contains {db_manager.get_collection_count()} vectors. Skipping embedding.")

    # 3. Initialize the Searcher
    searcher = HierarchicalSearcher(db_manager=db_manager, jsonl_path=jsonl_path)

    # 4. Enter the Interactive Evaluation Loop
    print("\n" + "="*60)
    print(" VERILOCAL RAG PIPELINE ACTIVE ".center(60, "="))
    print("="*60)
    print("Type your query below. Type 'exit' or 'quit' to shut down.\n")

    while True:
        try:
            query = input("Query > ").strip()
            if query.lower() in ['exit', 'quit']:
                print("Shutting down pipeline...")
                break
            if not query:
                continue

            # Execute Hierarchical Search
            results = searcher.search(query=query, top_k_micro=3)

            # Pretty-print the Evidence Pack
            print(f"\n--- EVIDENCE PACK (Found {len(results)} distinct Parent Contexts) ---")
            for i, res in enumerate(results, 1):
                print(f"\n[Result {i}] Distance: {res['distance']:.4f} | Page: {res['page_str']}")
                print(f"Section: {res['section_title']}")
                print(f"Micro Hit: \"...{res['micro_hit']}...\"")
                print("-" * 40)
                # Print just the first 300 chars of the full text to keep the terminal clean
                full_text = res['full_text']
                preview = full_text if len(full_text) < 300 else full_text[:300] + "... [TRUNCATED FOR CLI]"
                print(f"Context Passed to LLM:\n{preview}")
            print("\n" + "="*60 + "\n")

        except KeyboardInterrupt:
            print("\nShutting down pipeline...")
            break
        except Exception as e:
            logger.error(f"Search encountered an error: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the R-02 Retrieval CLI")
    parser.add_argument("jsonl_file", help="Path to the R-01 parsed JSONL file")
    parser.add_argument("--rebuild", action="store_true", help="Force a complete teardown and rebuild of the Chroma index")
    
    args = parser.parse_args()
    run_cli_orchestrator(args.jsonl_file, rebuild_index=args.rebuild)