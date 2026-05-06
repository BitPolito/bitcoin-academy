"""Document ingestion pipeline — QVAC-primary.

Flow: parse → chunk → JSONL → QVAC /ingest
ChromaDB is not written during ingestion. It remains as a passive fallback
at query time in chat_service.py if QVAC is unreachable.
"""
import json
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path and env constants
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_SERVICES_AI = _HERE.parents[2]          # services/ai/

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(_SERVICES_AI / "chroma_db"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "bitpolito_course")
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(_SERVICES_AI / "uploads")))
QVAC_INGEST_DIR = Path(os.getenv("QVAC_INGEST_DIR", str(_SERVICES_AI / "qvac_ingest")))
QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
# Set SKIP_CHROMA_INDEX=true to skip in-process embedding and ChromaDB write.
# Keep false only if you need the ChromaDB fallback populated for new documents.
SKIP_CHROMA_INDEX = os.getenv("SKIP_CHROMA_INDEX", "false").lower() == "true"

from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus  # noqa: E402
from app.db.session import get_db_context                                           # noqa: E402
from app.repositories import document_repo                                          # noqa: E402


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str) -> tuple[str, int]:
    """pymupdf4llm → structured Markdown + page count."""
    import pymupdf4llm
    import fitz
    text = pymupdf4llm.to_markdown(file_path)
    with fitz.open(file_path) as pdf:
        page_count = pdf.page_count
    return text, page_count


def parse_pptx(file_path: str) -> tuple[str, int]:
    """python-pptx → Markdown-like text with per-slide headings."""
    from pptx import Presentation
    prs = Presentation(file_path)
    slides = []
    for i, slide in enumerate(prs.slides, 1):
        title = (
            slide.shapes.title.text.strip()
            if slide.shapes.title and slide.shapes.title.has_text_frame
            else f"Slide {i}"
        )
        body_parts = []
        for shape in slide.placeholders:
            if (
                shape.has_text_frame
                and shape.placeholder_format is not None
                and shape.placeholder_format.idx != 0
            ):
                body_parts.append(shape.text_frame.text.strip())  # type: ignore[union-attr]
        body = "\n".join(p for p in body_parts if p)
        notes = ""
        if slide.has_notes_slide:
            nf = slide.notes_slide.notes_text_frame
            notes = nf.text.strip() if nf else ""
        parts = [f"## {title}"]
        if body:
            parts.append(body)
        if notes:
            parts.append(f"*Notes: {notes}*")
        slides.append("\n\n".join(parts))
    return "\n\n---\n\n".join(slides), len(prs.slides)


def parse_docx(file_path: str) -> tuple[str, int]:
    """python-docx → Markdown-like text with heading levels."""
    from docx import Document
    doc = Document(file_path)
    lines = []
    for para in doc.paragraphs:
        if not para.text.strip():
            continue
        style_name = (para.style.name or "") if para.style is not None else ""
        if style_name.startswith("Heading"):
            try:
                level = int(style_name.split()[-1])
            except ValueError:
                level = 2
            lines.append(f"{'#' * level} {para.text.strip()}")
        else:
            lines.append(para.text.strip())
    return "\n\n".join(lines), 0  # DOCX has no reliable page count


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

def chunk_text(text: str, doc_id: str) -> list[dict]:
    """chonkie TokenChunker → paragraph chunks as plain dicts."""
    from chonkie import TokenChunker
    chunker = TokenChunker(chunk_size=512, chunk_overlap=64)
    raw_chunks = chunker(text)
    return [
        {
            "id": f"{doc_id}_{i:04d}",
            "text": c.text,
            "chunk_type": "paragraph",
            "citation_label": f"chunk {i + 1}",
            "citation_page": 0,
            "citation_slide": 0,
            "citation_section": "",
            "doc_id": doc_id,
        }
        for i, c in enumerate(raw_chunks)
    ]


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _write_jsonl(chunks: list[dict], document_id: str) -> Path:
    QVAC_INGEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = QVAC_INGEST_DIR / f"{document_id}_contingency.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk) + "\n")
    logger.debug("Wrote %d chunks to %s", len(chunks), out_path)
    return out_path


# ---------------------------------------------------------------------------
# QVAC ingest
# ---------------------------------------------------------------------------

def _qvac_ingest(jsonl_path: Path, workspace: str, rebuild: bool = False) -> bool:
    """POST the JSONL path to QVAC for embedding + HyperDB indexing.

    Returns True on success, False on any network/HTTP error.
    Timeout configurable via QVAC_INGEST_TIMEOUT env (default 300s).
    """
    try:
        timeout = float(os.getenv("QVAC_INGEST_TIMEOUT", "300"))
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{QVAC_SERVICE_URL}/ingest",
                json={"jsonlPath": str(jsonl_path), "workspace": workspace, "rebuild": rebuild},
            )
            resp.raise_for_status()
            logger.info("QVAC ingest accepted — workspace '%s', status %d", workspace, resp.status_code)
            return True
    except httpx.HTTPError as exc:
        logger.warning("QVAC service unavailable, skipping QVAC ingest: %s", exc)
        return False


# ---------------------------------------------------------------------------
# DB helpers
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
# Public entry point — runs as a FastAPI BackgroundTask
# ---------------------------------------------------------------------------

def run(
    document_id: str,
    course_id: str,
    filename: str,
    file_path: str,
    material_type: str = "lecture",
) -> None:
    """Execute the full ingestion pipeline for an uploaded document."""
    logger.info("Pipeline starting for document %s (%s)", document_id, filename)

    with get_db_context() as db:
        doc = document_repo.get_by_id(db, document_id)
        if doc is None:
            logger.error("Document %s not found — aborting pipeline", document_id)
            return

        ext = Path(filename).suffix.lower()
        if ext not in {".pdf", ".pptx", ".docx"}:
            _mark_error(
                doc,
                f"Unsupported file type '{ext}'. Accepted: PDF, PPTX, DOCX.",
                db,
            )
            return

        try:
            # ------------------------------------------------------------------
            # Stage 1 — PARSING
            # ------------------------------------------------------------------
            _set_stage(doc, DocumentProcessingStage.PARSING, db)

            if ext == ".pdf":
                text, page_count = parse_pdf(file_path)
                parser_used = "pymupdf4llm"
            elif ext == ".pptx":
                text, page_count = parse_pptx(file_path)
                parser_used = "python-pptx"
            else:
                text, page_count = parse_docx(file_path)
                parser_used = "python-docx"

            # ------------------------------------------------------------------
            # Stage 2 — CHUNKING
            # ------------------------------------------------------------------
            _set_stage(doc, DocumentProcessingStage.CHUNKING, db)
            chunks = chunk_text(text, document_id)
            logger.info("Chunked %d paragraph chunks for %s", len(chunks), document_id)

            # ------------------------------------------------------------------
            # Stage 3 — INDEXING (ChromaDB — skipped when SKIP_CHROMA_INDEX=true)
            # ------------------------------------------------------------------
            _set_stage(doc, DocumentProcessingStage.INDEXING, db)

            if not SKIP_CHROMA_INDEX:
                from fastembed import TextEmbedding  # noqa: PLC0415
                import chromadb                      # noqa: PLC0415
                from chromadb.config import Settings as ChromaSettings  # noqa: PLC0415

                os.makedirs(CHROMA_DB_PATH, exist_ok=True)
                chroma_client = chromadb.PersistentClient(
                    path=CHROMA_DB_PATH,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                collection = chroma_client.get_or_create_collection(
                    name=CHROMA_COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
                embedding_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
                texts = [c["text"] for c in chunks]
                embeddings = [v.tolist() for v in embedding_model.embed(texts)]
                ids = [c["id"] for c in chunks]
                metadatas = [
                    {
                        "doc_id": c["doc_id"],
                        "filename": filename,
                        "course_id": course_id,
                        "material_type": material_type,
                        "label": c["citation_label"],
                        "section": c["citation_section"],
                        "page": c["citation_page"],
                        "slide": c["citation_slide"],
                        "chunk_type": c["chunk_type"],
                    }
                    for c in chunks
                ]
                if ids:
                    collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        documents=texts,
                        metadatas=metadatas,  # type: ignore[arg-type]
                    )
                    logger.info("Indexed %d vectors into ChromaDB at %s", len(ids), CHROMA_DB_PATH)
            else:
                logger.info("SKIP_CHROMA_INDEX=true — skipping ChromaDB embedding for %s", document_id)

            # ------------------------------------------------------------------
            # Stage 4 — QVAC ingest
            # ------------------------------------------------------------------
            jsonl_path = _write_jsonl(chunks, document_id)
            qvac_ok = _qvac_ingest(jsonl_path, workspace=course_id, rebuild=False)

            # ------------------------------------------------------------------
            # Finalise DB record
            # ------------------------------------------------------------------
            sections = re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)[:20]
            sample = [
                {
                    "text": c["text"][:300],
                    "label": c["citation_label"],
                    "section": c["citation_section"],
                }
                for c in chunks[:5]
            ]

            doc.status = DocumentStatus.READY
            doc.processing_stage = DocumentProcessingStage.DONE
            doc.indexing_status = "indexed" if qvac_ok else "qvac_pending"
            doc.chunk_count = len(chunks)
            doc.parser_used = parser_used
            doc.page_count = page_count if page_count else None
            doc.extracted_text_preview = text[:500]
            doc.sections_json = json.dumps(sections)
            doc.sample_chunks_json = json.dumps(sample)
            db.commit()

            logger.info(
                "Pipeline done for %s — %d chunks, parser=%s, qvac_ok=%s",
                document_id, len(chunks), parser_used, qvac_ok,
            )

            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                pass

        except Exception as exc:
            logger.exception("Pipeline failed for %s: %s", document_id, exc)
            _mark_error(doc, str(exc), db)


# ---------------------------------------------------------------------------
# QVAC-only reindex — retries the QVAC ingest step without re-parsing
# ---------------------------------------------------------------------------

def reindex_qvac(document_id: str, course_id: str) -> None:
    """Retry QVAC ingest for a document whose indexing_status is 'qvac_pending'."""
    jsonl_path = QVAC_INGEST_DIR / f"{document_id}_contingency.jsonl"
    if not jsonl_path.exists():
        logger.warning(
            "Cannot reindex %s: JSONL not found at %s", document_id, jsonl_path
        )
        return

    with get_db_context() as db:
        doc = document_repo.get_by_id(db, document_id)
        if doc is None:
            logger.error("Document %s not found — aborting reindex", document_id)
            return

        qvac_ok = _qvac_ingest(jsonl_path, workspace=course_id, rebuild=True)
        doc.indexing_status = "indexed" if qvac_ok else "qvac_pending"
        db.commit()
        logger.info(
            "Reindex QVAC for %s: indexing_status=%s", document_id, doc.indexing_status
        )
