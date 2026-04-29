"""Document processing pipeline — stages: PARSING → CHUNKING → INDEXING → DONE.

Bridges the FastAPI backend with the standalone ingester modules in
workers/python-ingester/src/ without duplicating their logic.

Import-conflict guard: registers 'services.ai.app.schemas.normalized_document'
in sys.modules as an alias for the already-loaded 'app.schemas.normalized_document'
so that ingester modules that use the longer import path get the *same* class
objects as the rest of the FastAPI app.

QVAC integration: after chunking, paragraph chunks are written to a JSONL file
and posted to the QVAC Node.js service for embedding + HyperDB indexing.
If the QVAC service is not running the pipeline still completes — ChromaDB
remains the active query path until chat_service.py is switched over.
"""
import json
import logging
import os
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Monorepo path constants
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_SERVICES_AI = _HERE.parents[2]          # services/ai/
_MONOREPO_ROOT = _SERVICES_AI.parents[1] # bitcoin-academy/
_INGESTER_SRC = _MONOREPO_ROOT / "workers" / "python-ingester" / "src"

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(_SERVICES_AI / "chroma_db"))
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(_SERVICES_AI / "uploads")))

# JSONL files are written here so the QVAC service can read them by absolute path.
QVAC_INGEST_DIR = Path(os.getenv("QVAC_INGEST_DIR", str(_SERVICES_AI / "qvac_ingest")))
QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")


# ---------------------------------------------------------------------------
# sys.modules aliasing — must run before any ingester import
# ---------------------------------------------------------------------------
def _alias_schema_module() -> None:
    """Alias app.schemas.normalized_document under the services.ai.app.* path.

    Ingester modules use 'from services.ai.app.schemas.normalized_document import …'
    while FastAPI uses 'from app.schemas.normalized_document import …'.
    Without aliasing these would be different module objects, causing Pydantic
    isinstance checks to fail silently.
    """
    import importlib
    nd = importlib.import_module("app.schemas.normalized_document")

    chain = [
        "services",
        "services.ai",
        "services.ai.app",
        "services.ai.app.schemas",
    ]
    for name in chain:
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = []
            pkg.__package__ = name
            parent, _, child = name.rpartition(".")
            if parent and parent in sys.modules:
                setattr(sys.modules[parent], child, pkg)
            sys.modules[name] = pkg

    sys.modules["services.ai.app.schemas.normalized_document"] = nd


_alias_schema_module()

# Add ingester src to path so module_*.py / retrieval_*.py can be imported
if str(_INGESTER_SRC) not in sys.path:
    sys.path.insert(0, str(_INGESTER_SRC))

# ---------------------------------------------------------------------------
# Lazy ingester imports (after path + alias setup)
# ---------------------------------------------------------------------------
from module_1_ingestor import RamSafeIngestor       # noqa: E402
from module_2_parser import StructuralParser         # noqa: E402
from module_3_micro_chunker import Chunker  # noqa: E402

from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus
from app.db.session import get_db_context
from app.repositories import document_repo
from app.schemas.normalized_document import ChunkType, DocumentType


# ---------------------------------------------------------------------------
# QVAC helpers
# ---------------------------------------------------------------------------

def _write_qvac_jsonl(chunks: list, document_id: str) -> Path:
    """Serialize paragraph chunks to a JSONL file readable by the QVAC service.

    Uses course_id as workspace identifier, matching the convention in ingest.js.
    Returns the absolute path written.
    """
    QVAC_INGEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = QVAC_INGEST_DIR / f"{document_id}_contingency.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk.model_dump(mode="json")) + "\n")
    logger.debug("Wrote %d chunks to %s", len(chunks), out_path)
    return out_path


def _qvac_ingest(jsonl_path: Path, workspace: str, rebuild: bool = False) -> None:
    """POST the JSONL path to the QVAC service for embedding + HyperDB indexing.

    Non-blocking best-effort: logs a warning on failure so the pipeline
    continues even when the QVAC Node.js service is not running.
    """
    payload = json.dumps({
        "jsonlPath": str(jsonl_path),
        "workspace": workspace,
        "rebuild": rebuild,
    }).encode()
    req = urllib.request.Request(
        f"{QVAC_SERVICE_URL}/ingest",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("QVAC ingest accepted — workspace '%s', status %d", workspace, resp.status)
    except urllib.error.URLError as exc:
        # Service not running or unreachable — not a pipeline error.
        logger.warning("QVAC service unavailable, skipping QVAC ingest: %s", exc.reason)
    except Exception as exc:
        logger.warning("QVAC ingest failed: %s", exc)


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

def run(document_id: str, course_id: str, filename: str, file_path: str) -> None:
    """Execute the full ingestion pipeline for an uploaded document.

    Opens its own DB session so it is safe to run after the request session
    has been closed by FastAPI.
    """
    logger.info("Pipeline starting for document %s (%s)", document_id, filename)

    with get_db_context() as db:
        doc = document_repo.get_by_id(db, document_id)
        if doc is None:
            logger.error("Document %s not found — aborting pipeline", document_id)
            return

        try:
            # ------------------------------------------------------------------
            # Stage 1 — PARSING + CHUNKING
            # ------------------------------------------------------------------
            _set_stage(doc, DocumentProcessingStage.PARSING, db)

            is_pptx = filename.lower().endswith(".pptx")
            doc_type = DocumentType.LECTURE_SLIDES if is_pptx else DocumentType.TEXTBOOK_EXCERPT
            doc_title = os.path.splitext(filename)[0]

            ingestor = RamSafeIngestor(file_path=file_path, chunk_size=100)
            parser = StructuralParser(
                file_path=file_path,
                use_advanced_parser=False,
                course_id=course_id,
                document_id=document_id,
                document_type=doc_type,
                title=doc_title,
                source_filename=filename,
                lecture_id=document_id,
            )
            chunker = Chunker(max_char_limit=1500)

            all_chunks: list = []
            last_normalized_doc = None

            def _process_batch(pages) -> None:
                nonlocal last_normalized_doc
                normalized = parser.parse_pages(pages, ingestor.total_pages)
                last_normalized_doc = normalized
                all_chunks.extend(chunker.process_document(normalized))

            ingestor.process_in_batches(_process_batch)

            _set_stage(doc, DocumentProcessingStage.CHUNKING, db)
            para_chunks = [c for c in all_chunks if c.chunk_type == ChunkType.PARAGRAPH]
            logger.info(
                "Parsed %d total chunks (%d paragraph) for %s",
                len(all_chunks), len(para_chunks), document_id,
            )

            # ------------------------------------------------------------------
            # Stage 2 — EMBEDDING + INDEXING
            # ------------------------------------------------------------------
            _set_stage(doc, DocumentProcessingStage.INDEXING, db)

            # Import here so server startup does not fail if deps are missing
            from fastembed import TextEmbedding  # noqa: PLC0415
            import chromadb                      # noqa: PLC0415
            from chromadb.config import Settings as ChromaSettings  # noqa: PLC0415

            os.makedirs(CHROMA_DB_PATH, exist_ok=True)
            chroma_client = chromadb.PersistentClient(
                path=CHROMA_DB_PATH,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            collection = chroma_client.get_or_create_collection(
                name="bitpolito_course",
                metadata={"hnsw:space": "cosine"},
            )

            embedding_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
            texts = [c.text for c in para_chunks]
            embeddings = [v.tolist() for v in embedding_model.embed(texts)]
            ids = [c.chunk_id for c in para_chunks]
            metadatas = [
                {
                    "doc_id": c.doc_id,
                    "course_id": c.course_id,
                    "lecture_id": c.lecture_id or c.doc_id,
                    "document_type": c.document_type.value,
                    "label": c.citation_label,
                    "section": c.citation_section or "N/A",
                    "page": c.citation_page or 0,
                    "slide": c.citation_slide or 0,
                    "chunk_type": c.chunk_type.value,
                    "parent_chunk_id": c.parent_chunk_id or "",
                    "tags": ",".join(c.tags),
                    "prerequisites": ",".join(c.prerequisites),
                }
                for c in para_chunks
            ]

            if ids:
                collection.add(  # type: ignore[arg-type]
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )
                logger.info("Indexed %d vectors into ChromaDB at %s", len(ids), CHROMA_DB_PATH)

            # ------------------------------------------------------------------
            # Stage 3 — QVAC ingest (best-effort; pipeline succeeds even if skipped)
            # ------------------------------------------------------------------
            jsonl_path = _write_qvac_jsonl(para_chunks, document_id)
            _qvac_ingest(jsonl_path, workspace=course_id, rebuild=True)

            # ------------------------------------------------------------------
            # Finalise DB record
            # ------------------------------------------------------------------
            nd = last_normalized_doc
            section_titles = sorted({
                c.citation_section for c in para_chunks if c.citation_section
            })
            sample = [
                {
                    "text": c.text[:300],
                    "label": c.citation_label,
                    "section": c.citation_section,
                }
                for c in para_chunks[:5]
            ]

            doc.status = DocumentStatus.READY
            doc.processing_stage = DocumentProcessingStage.DONE
            doc.chunk_count = len(para_chunks)
            doc.parser_used = nd.parser_used if nd else "unknown"
            doc.page_count = nd.page_count if nd else None
            doc.extracted_text_preview = nd.blocks[0].text[:500] if nd and nd.blocks else ""
            doc.sections_json = json.dumps(section_titles)
            doc.sample_chunks_json = json.dumps(sample)
            db.commit()

            logger.info("Pipeline done for %s — %d paragraph chunks indexed", document_id, len(para_chunks))

        except Exception as exc:
            logger.exception("Pipeline failed for %s: %s", document_id, exc)
            _mark_error(doc, str(exc), db)

        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug("Cleaned up temp file: %s", file_path)
            except OSError:
                pass
