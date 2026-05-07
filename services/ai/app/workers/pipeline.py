"""Document ingestion pipeline — QVAC-primary, structure-aware chunking.

Flow: parse (page-by-page) → clean → chunk (structure-aware) → filter → JSONL → QVAC /ingest
ChromaDB is not written during ingestion. It remains as a passive fallback
at query time in chat_service.py if QVAC is unreachable.
"""
import json
import logging
import os
import re
from collections import Counter
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
SKIP_CHROMA_INDEX = os.getenv("SKIP_CHROMA_INDEX", "false").lower() == "true"

from app.db.models import CourseDocument, DocumentProcessingStage, DocumentStatus  # noqa: E402
from app.db.session import get_db_context                                           # noqa: E402
from app.repositories import document_repo                                          # noqa: E402

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------
_MAX_WORDS = 400        # soft cap per chunk normale (≈ 512 token)
_MIN_WORDS = 25         # soglia paragrafi: chunk più corti vengono scartati
_MIN_WORDS_TABLE = 4    # soglia tabelle: basta una riga dati (celle corte)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    return len(text.split())


_FIGURE_CAPTION_RE = re.compile(r'_Figure\s+[\d][\d.-]*[^_]*_', re.IGNORECASE)

# Patterns da rimuovere da ogni pagina
_STRIP_PATTERNS = [
    re.compile(r'www\.\S+\.ir\b[^\S\n]*', re.IGNORECASE),       # watermark EBooksWorld e simili
    re.compile(r'www\.\S+\.com/?\s*\n', re.IGNORECASE),          # altri watermark URL inline
    re.compile(r'^\s*\d+\s*\|\s*Chapter[^\n]*', re.MULTILINE),   # "8 | Chapter 1: Introduction"
    re.compile(r'[­​‌‍﻿]'),                                         # unicode invisibili (soft-hyphen, ZWS, ecc.)
]

# Regex per sentence splitting (fine frase + inizio maiuscola)
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z\"])')


# ---------------------------------------------------------------------------
# Stage 1 — Parsers (page-by-page)
# ---------------------------------------------------------------------------

def parse_pdf_pages(file_path: str) -> tuple[list[dict], int]:
    """pymupdf4llm page_chunks=True → [{page, text}] + page count.

    Ogni elemento corrisponde a una pagina PDF con il suo numero (1-indexed).
    """
    import pymupdf4llm
    import fitz

    raw = pymupdf4llm.to_markdown(file_path, page_chunks=True)
    pages = []
    for p in raw:
        meta = p.get("metadata", {}) if isinstance(p, dict) else {}
        # get_metadata in pymupdf4llm sets page = pno + 1 (already 1-indexed)
        page_num = meta.get("page", 0)
        text = p.get("text", "") if isinstance(p, dict) else str(p)
        pages.append({"page": page_num, "text": text})

    with fitz.open(file_path) as pdf:
        page_count = pdf.page_count

    return pages, page_count


def parse_pptx_pages(file_path: str) -> tuple[list[dict], int]:
    """python-pptx → [{page=slide_num, text}] per ogni slide."""
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
        slides.append({"page": i, "text": "\n\n".join(parts)})

    return slides, len(prs.slides)


def parse_docx_pages(file_path: str) -> tuple[list[dict], int]:
    """python-docx → singola entry [{page=1, text}] (nessun page count affidabile)."""
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

    return [{"page": 1, "text": "\n\n".join(lines)}], 0


# ---------------------------------------------------------------------------
# Stage 2 — Cleaner
# ---------------------------------------------------------------------------

def detect_boilerplate(pages: list[dict], min_freq: float = 0.3) -> set[str]:
    """Identifica righe che compaiono in >= min_freq delle pagine (header/footer).

    Ritorna un set di stringhe stripped da rimuovere durante il cleaning.
    Ignorato per documenti con < 5 pagine (troppo poco campione).
    """
    if len(pages) < 5:
        return set()

    line_counts: Counter = Counter()
    for p in pages:
        seen_on_page: set[str] = set()
        for line in p["text"].splitlines():
            s = line.strip()
            if s and len(s) > 3:
                seen_on_page.add(s)
        line_counts.update(seen_on_page)

    threshold = len(pages) * min_freq
    return {line for line, count in line_counts.items() if count >= threshold}


def clean_page(text: str, boilerplate: set[str]) -> str:
    """Rimuove watermark, boilerplate ripetuti e unicode invisibili da una pagina."""
    # Rimuovi pattern fissi
    for pat in _STRIP_PATTERNS:
        text = pat.sub("", text)

    # Rimuovi righe di boilerplate rilevate automaticamente
    if boilerplate:
        lines = []
        for line in text.splitlines():
            if line.strip() not in boilerplate:
                lines.append(line)
        text = "\n".join(lines)

    # Comprimi newline multipli
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Stage 3 — Structure-aware chunker
# ---------------------------------------------------------------------------

def _split_into_blocks(text: str) -> list[dict]:
    """Segmenta il testo in blocchi tipizzati: heading | table | paragraph.

    Le tabelle markdown (righe con |) vengono preservate come blocco atomico.
    """
    blocks: list[dict] = []
    current_type: str = "paragraph"
    current_lines: list[str] = []

    def flush() -> None:
        if current_lines:
            t = "".join(current_lines).strip()
            if t:
                blocks.append({"type": current_type, "text": t})
            current_lines.clear()

    for line in text.splitlines(keepends=True):
        stripped = line.strip()

        if re.match(r'^#{1,4}\s+\S', stripped):
            flush()
            blocks.append({"type": "heading", "text": stripped})
        elif stripped.startswith("|"):
            if current_type != "table":
                flush()
                current_type = "table"
            current_lines.append(line)
        else:
            if current_type == "table":
                # Una riga vuota o non-tabella chiude la tabella
                if not stripped:
                    flush()
                    current_type = "paragraph"
                else:
                    # Riga di testo subito dopo tabella (es. nota): chiudi tabella
                    flush()
                    current_type = "paragraph"
                    current_lines.append(line)
            else:
                current_type = "paragraph"
                current_lines.append(line)

    flush()
    return blocks


def _split_paragraph(text: str, max_words: int) -> list[str]:
    """Divide un paragrafo lungo in sub-chunk ancorati a fine frase.

    Nessun overlap: ogni sub-chunk è autonomo e inizia a inizio frase.
    """
    if _word_count(text) <= max_words:
        return [text]

    sentences = _SENTENCE_SPLIT_RE.split(text)
    result: list[str] = []
    current: list[str] = []
    current_words = 0

    for sent in sentences:
        sent_words = _word_count(sent)
        if current_words + sent_words > max_words and current:
            result.append(" ".join(current))
            current, current_words = [], 0
        current.append(sent)
        current_words += sent_words

    if current:
        result.append(" ".join(current))

    return result


def _make_chunk(
    doc_id: str,
    page: int,
    idx: int,
    text: str,
    chunk_type: str,
    section: str,
) -> dict:
    return {
        "id": f"{doc_id}_{page:04d}_{idx:04d}",
        "text": text,
        "chunk_type": chunk_type,
        "citation_label": f"p. {page}",
        "citation_page": page,
        "citation_slide": 0,
        "citation_section": section,
        "doc_id": doc_id,
    }


def chunk_pages(pages: list[dict], doc_id: str) -> list[dict]:
    """Chunking structure-aware: heading → table → paragraph con sentence split.

    Ogni chunk porta il numero di pagina e la sezione corrente.
    Nessun overlap: la sezione corrente è già contesto sufficiente.
    """
    chunks: list[dict] = []
    current_section = ""
    chunk_idx = 0

    for page_data in pages:
        page_num = page_data["page"]
        text = page_data["text"]

        if not text.strip():
            continue

        blocks = _split_into_blocks(text)
        pending_heading = ""

        for block in blocks:
            btype = block["type"]
            btext = block["text"].strip()

            if not btext:
                continue

            if btype == "heading":
                # Accumula heading; la sezione viene aggiornata al primo paragrafo/tabella seguente
                heading_text = re.sub(r'^#{1,4}\s+', '', btext).strip()
                current_section = heading_text
                pending_heading = btext
                continue

            if btype == "table":
                # Prepend heading se in attesa
                full_text = f"{pending_heading}\n\n{btext}" if pending_heading else btext
                pending_heading = ""
                if _word_count(full_text) >= _MIN_WORDS_TABLE:
                    chunks.append(_make_chunk(doc_id, page_num, chunk_idx, full_text, "table", current_section))
                    chunk_idx += 1
                continue

            # Paragrafo — eventualmente prepend heading
            full_text = f"{pending_heading}\n\n{btext}" if pending_heading else btext
            pending_heading = ""

            for sub in _split_paragraph(full_text, _MAX_WORDS):
                sub = sub.strip()
                if _word_count(sub) >= _MIN_WORDS:
                    chunks.append(_make_chunk(doc_id, page_num, chunk_idx, sub, "paragraph", current_section))
                    chunk_idx += 1

        # Heading rimasto senza corpo (ultima riga della pagina): ignoralo,
        # la sezione corrente è già aggiornata per la pagina seguente.

    return chunks


# ---------------------------------------------------------------------------
# Stage 4 — Quality filter
# ---------------------------------------------------------------------------

def filter_chunks(chunks: list[dict]) -> list[dict]:
    """Scarta chunk di qualità insufficiente.

    Criteri di scarto:
    - Paragrafi con meno di _MIN_WORDS parole
    - Tabelle con meno di _MIN_WORDS_TABLE parole
    - Chunk dominati da caption figura (> 60% dei caratteri)
    """
    result = []
    for c in chunks:
        text = c["text"]
        is_table = c.get("chunk_type") == "table"
        threshold = _MIN_WORDS_TABLE if is_table else _MIN_WORDS

        if _word_count(text) < threshold:
            continue

        caption_chars = sum(len(m.group()) for m in _FIGURE_CAPTION_RE.finditer(text))
        if len(text) > 0 and caption_chars / len(text) > 0.6:
            continue

        result.append(c)

    return result


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
# Public entry point
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
            _mark_error(doc, f"Unsupported file type '{ext}'. Accepted: PDF, PPTX, DOCX.", db)
            return

        try:
            # ------------------------------------------------------------------
            # Stage 1 — PARSING (page-by-page)
            # ------------------------------------------------------------------
            _set_stage(doc, DocumentProcessingStage.PARSING, db)

            if ext == ".pdf":
                pages, page_count = parse_pdf_pages(file_path)
                parser_used = "pymupdf4llm-page-chunks"
            elif ext == ".pptx":
                pages, page_count = parse_pptx_pages(file_path)
                parser_used = "python-pptx"
            else:
                pages, page_count = parse_docx_pages(file_path)
                parser_used = "python-docx"

            logger.info("Parsed %d pages for %s", len(pages), document_id)

            # ------------------------------------------------------------------
            # Stage 2 — CLEANING (PDF only; PPTX/DOCX are already clean)
            # ------------------------------------------------------------------
            if ext == ".pdf":
                boilerplate = detect_boilerplate(pages)
                if boilerplate:
                    logger.info("Detected %d boilerplate lines for %s", len(boilerplate), document_id)
                pages = [
                    {"page": p["page"], "text": clean_page(p["text"], boilerplate)}
                    for p in pages
                ]

            # ------------------------------------------------------------------
            # Stage 3 — CHUNKING (structure-aware)
            # ------------------------------------------------------------------
            _set_stage(doc, DocumentProcessingStage.CHUNKING, db)
            raw_chunks = chunk_pages(pages, document_id)

            # ------------------------------------------------------------------
            # Stage 4 — QUALITY FILTER
            # ------------------------------------------------------------------
            chunks = filter_chunks(raw_chunks)
            dropped = len(raw_chunks) - len(chunks)
            logger.info(
                "Chunks for %s: %d raw → %d after filter (%d dropped)",
                document_id, len(raw_chunks), len(chunks), dropped,
            )

            # ------------------------------------------------------------------
            # Stage 5 — INDEXING (ChromaDB — skipped when SKIP_CHROMA_INDEX=true)
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
            # Stage 6 — QVAC ingest
            # ------------------------------------------------------------------
            jsonl_path = _write_jsonl(chunks, document_id)
            qvac_ok = _qvac_ingest(jsonl_path, workspace=course_id, rebuild=False)

            # ------------------------------------------------------------------
            # Finalise DB record
            # ------------------------------------------------------------------
            full_text = "\n\n".join(p["text"] for p in pages)
            sections = list(dict.fromkeys(          # dedup preserving order
                c["citation_section"] for c in chunks if c["citation_section"]
            ))[:20]
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
            doc.extracted_text_preview = full_text[:500]
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
        logger.warning("Cannot reindex %s: JSONL not found at %s", document_id, jsonl_path)
        return

    with get_db_context() as db:
        doc = document_repo.get_by_id(db, document_id)
        if doc is None:
            logger.error("Document %s not found — aborting reindex", document_id)
            return

        qvac_ok = _qvac_ingest(jsonl_path, workspace=course_id, rebuild=True)
        doc.indexing_status = "indexed" if qvac_ok else "qvac_pending"
        db.commit()
        logger.info("Reindex QVAC for %s: indexing_status=%s", document_id, doc.indexing_status)
