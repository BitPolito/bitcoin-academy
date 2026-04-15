import sys
import logging
from module_1_ingestor import RamSafeIngestor
from module_2_parser import StructuralParser
from module_3_micro_chunker import VerilocalMicroChunker
from module_4_exporter import JsonlExporter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_extraction_pipeline(file_path: str, course_id: str, document_id: str):
    logger.info(f"Initializing Verilocal Pipeline for: {file_path}")
    
    # Initialize Modules
    ingestor = RamSafeIngestor(file_path=file_path, chunk_size=100)
    parser = StructuralParser(course_id=course_id, document_id=document_id)
    micro_chunker = VerilocalMicroChunker(max_char_limit=8000, chunk_size=500, overlap=50)
    exporter = JsonlExporter(output_dir="./parsed_output")

    # This callback is executed for every 100-page slice safely loaded into RAM
    def process_batch(pages):
        # Step 2: Extract Structure
        structural_chunks = parser.parse_pages(pages)
        
        # Step 3: Apply Guillotine & Micro-chunking
        final_chunks = micro_chunker.process_chunks(structural_chunks)
        
        # Step 4: Sanitize and write to SSD
        exporter.sanitize_and_export(final_chunks, document_id)

    # Start the engine
    ingestor.process_in_batches(process_batch)
    logger.info(f"Pipeline complete. Output saved to ./parsed_output/{document_id}_contingency.jsonl")

if __name__ == "__main__":
    # Quick CLI for your testing
    if len(sys.argv) < 2:
        print("Usage: python main_pipeline.py <path_to_pdf>")
        sys.exit(1)
        
    test_pdf = sys.argv[1]
    run_extraction_pipeline(test_pdf, course_id="TEST_COURSE", document_id="TEST_DOC_001")