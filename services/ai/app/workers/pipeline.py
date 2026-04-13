"""Document processing pipeline.

Stages: PARSING -> NORMALIZING -> CHUNKING -> INDEXING -> DONE
Each stage updates the document record before proceeding.
All heavy-lifting functions are stubs to be replaced with real implementations.
"""
import logging
from typing import List

from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus
from app.db.session import get_db_context
from app.repositories import document_repo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline stages (stubs — replace with real implementations)
# ---------------------------------------------------------------------------

def _parse(filename: str) -> str:
    """Extract raw text from the document. Currently returns a stub."""
    logger.info("Pipeline [1/4] parsing: %s", filename)
    if not filename.lower().endswith(".pdf"):
        raise ValueError(f"Unsupported file type: {filename}")
    return (
        "Bitcoin is a peer-to-peer electronic cash system that allows online "
        "payments to be sent directly from one party to another without "
        "going through a financial institution."
    )


def _chunk(text: str) -> List[str]:
    """Split text into overlapping chunks. Currently returns stubs."""
    logger.info("Pipeline [2/4] chunking")
    return ["chunk_1", "chunk_2", "chunk_3"]


def _embed(chunks: List[str]) -> List[List[float]]:
    """Produce dense vector embeddings for each chunk. Currently returns stubs."""
    logger.info("Pipeline [3/4] embedding")
    return [[0.1 * (i + 1), 0.2 * (i + 1)] for i in range(len(chunks))]


def _index(vectors: List[List[float]], course_id: str) -> bool:
    """Store vectors in the vector database. Currently a no-op stub."""
    logger.info("Pipeline [4/4] indexing into course %s", course_id)
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_stage(doc: CourseDocument, stage: DocumentProcessingStage, db) -> None:
    doc.processing_stage = stage
    db.commit()


def _mark_error(doc: CourseDocument, message: str, db) -> None:
    doc.status = DocumentStatus.ERROR
    doc.processing_stage = DocumentProcessingStage.ERROR
    doc.error_message = message
    db.commit()


# ---------------------------------------------------------------------------
# Public entry point — designed to run in a background task
# ---------------------------------------------------------------------------

def run(document_id: str, course_id: str, filename: str) -> None:
    """Execute the full processing pipeline for a document.

    Opens its own database session so it is safe to run as a FastAPI
    BackgroundTask (after the request session has been closed).
    """
    logger.info("Pipeline starting for document %s", document_id)

    with get_db_context() as db:
        doc = document_repo.get_by_id(db, document_id)
        if doc is None:
            logger.error("Document %s not found — aborting pipeline", document_id)
            return

        try:
            _set_stage(doc, DocumentProcessingStage.PARSING, db)
            text = _parse(filename)

            _set_stage(doc, DocumentProcessingStage.CHUNKING, db)
            chunks = _chunk(text)

            _set_stage(doc, DocumentProcessingStage.INDEXING, db)
            _index(_embed(chunks), course_id)

            doc.status = DocumentStatus.READY
            doc.processing_stage = DocumentProcessingStage.DONE
            doc.chunk_count = len(chunks)
            doc.extracted_text_preview = text[:500]
            db.commit()
            logger.info("Pipeline completed for document %s", document_id)

        except Exception as exc:
            logger.exception("Pipeline failed for document %s: %s", document_id, exc)
            _mark_error(doc, str(exc), db)
