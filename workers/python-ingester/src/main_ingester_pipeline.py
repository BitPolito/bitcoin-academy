import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)

services_ai_root = os.path.join(project_root, "services", "ai")
sys.path.insert(0, services_ai_root)

import logging
from module_1_ingestor import RamSafeIngestor
from module_2_parser import StructuralParser
from module_3_micro_chunker import VerilocalChunker
from module_4_exporter import JsonlExporter
from services.ai.app.schemas.normalized_document import DocumentType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_extraction_pipeline(file_path: str, course_id: str, document_id: str, doc_type: DocumentType):
    logger.info(f"Initializing Schema-Compliant Pipeline for: {file_path}")
    
    ingestor = RamSafeIngestor(file_path=file_path, chunk_size=100)
    # The parser now builds a formal NormalizedDocument
    parser = StructuralParser(
        course_id=course_id, 
        document_id=document_id, 
        document_type=doc_type,
        title="Dive Into Deep Learning",
        source_filename=file_path
    )
    chunker = VerilocalChunker(max_char_limit=1500)
    exporter = JsonlExporter(output_dir="./parsed_output")

    def process_batch(pages):
        # We pass total_pages so the NormalizedDocument metadata is accurate
        normalized_doc = parser.parse_pages(pages, ingestor.total_pages)
        document_chunks = chunker.process_document(normalized_doc)
        exporter.export_chunks(document_chunks, document_id)

    ingestor.process_in_batches(process_batch)
    logger.info(f"Pipeline complete. Output saved to ./parsed_output/{document_id}_contingency.jsonl")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python src/main_ingester_pipeline.py <path_to_file>")
        sys.exit(1)
        
    target_file = sys.argv[1]
    
    # --- AUTO-DETECT FILE TYPE AND ASSIGN SCHEMA ---
    if target_file.lower().endswith('.pptx'):
        selected_type = DocumentType.LECTURE_SLIDES
        doc_id = "TEST_SLIDES_001"
        logger.info("Auto-detected PPTX: Routing to LECTURE_SLIDES schema.")
    else:
        selected_type = DocumentType.TEXTBOOK_EXCERPT
        doc_id = "TEST_DOC_001"
        logger.info("Auto-detected PDF: Routing to TEXTBOOK_EXCERPT schema.")
    
    # Run the pipeline with the correct schema
    run_extraction_pipeline(
        file_path=target_file, 
        course_id="TEST_COURSE", 
        document_id=doc_id, 
        doc_type=selected_type
    )
    