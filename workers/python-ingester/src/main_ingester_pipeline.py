import sys
import os
import argparse

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)

services_ai_root = os.path.join(project_root, "services", "ai")
sys.path.insert(0, services_ai_root)

import logging
from module_1_ingestor import RamSafeIngestor
from module_2_parser import StructuralParser
from module_3_micro_chunker import Chunker
from module_4_exporter import JsonlExporter
from services.ai.app.schemas.normalized_document import DocumentType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_extraction_pipeline(
    file_path: str,
    course_id: str,
    document_id: str,
    doc_type: DocumentType,
    use_docling: bool = False,
    lecture_id: str | None = None,
    tags: list[str] | None = None,
    prerequisites: list[str] | None = None,
):
    logger.info(f"Initializing pipeline for: {file_path} (docling={use_docling})")

    ingestor = RamSafeIngestor(file_path=file_path, chunk_size=100)
    parser = StructuralParser(
        file_path=file_path,
        use_advanced_parser=use_docling,
        course_id=course_id,
        document_id=document_id,
        document_type=doc_type,
        title=os.path.splitext(os.path.basename(file_path))[0],
        source_filename=os.path.basename(file_path),
        lecture_id=lecture_id,
        tags=tags or [],
        prerequisites=prerequisites or [],
    )
    chunker = Chunker(max_char_limit=1500)
    exporter = JsonlExporter(output_dir="./parsed_output")

    # Clear existing output for this document so re-runs don't append duplicates
    out_path = os.path.join("./parsed_output", f"{document_id}_contingency.jsonl")
    if os.path.exists(out_path):
        os.remove(out_path)

    def process_batch(pages):
        normalized_doc = parser.parse_pages(pages, ingestor.total_pages)
        document_chunks = chunker.process_document(normalized_doc)
        exporter.export_chunks(document_chunks, document_id)

    ingestor.process_in_batches(process_batch)
    logger.info(f"Pipeline complete. Output: ./parsed_output/{document_id}_contingency.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="BP-Academy ingestion pipeline")
    ap.add_argument("file", help="Path to PDF or PPTX course file")
    ap.add_argument("--docling", action="store_true", help="Use Docling as primary parser")
    ap.add_argument("--course-id", default="TEST_COURSE", help="Course identifier")
    ap.add_argument("--doc-id", default=None, help="Document identifier (auto-derived if omitted)")
    ap.add_argument("--lecture-id", default=None, help="Lecture ID within the course (defaults to doc-id)")
    ap.add_argument("--tags", default="", help="Comma-separated topic tags (e.g. 'cryptography,hashing')")
    ap.add_argument("--prerequisites", default="", help="Comma-separated prerequisite labels (e.g. 'public-key-crypto')")
    args = ap.parse_args()

    target_file = args.file

    if target_file.lower().endswith('.pptx'):
        selected_type = DocumentType.LECTURE_SLIDES
        auto_id = "SLIDES_" + os.path.splitext(os.path.basename(target_file))[0].upper()
        logger.info("Auto-detected PPTX → LECTURE_SLIDES schema.")
    else:
        selected_type = DocumentType.TEXTBOOK_EXCERPT
        auto_id = "DOC_" + os.path.splitext(os.path.basename(target_file))[0].upper()
        logger.info("Auto-detected PDF → TEXTBOOK_EXCERPT schema.")

    doc_id = args.doc_id or auto_id
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    prerequisites = [p.strip() for p in args.prerequisites.split(",") if p.strip()]

    run_extraction_pipeline(
        file_path=target_file,
        course_id=args.course_id,
        document_id=doc_id,
        doc_type=selected_type,
        use_docling=args.docling,
        lecture_id=args.lecture_id,
        tags=tags,
        prerequisites=prerequisites,
    )
