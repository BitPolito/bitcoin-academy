"""Debug API — internal visibility endpoints, active only when DEBUG_MODE=true."""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import document_repo
from app.schemas.evidence_pack import EvidencePack
from app.services import evidence_pack_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["Debug"])

_HERE = Path(__file__).resolve()
_SERVICES_AI = _HERE.parents[2]
_INGESTER_SRC = _SERVICES_AI.parents[1] / "workers" / "python-ingester" / "src"
_CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(_SERVICES_AI / "chroma_db"))


# ---------------------------------------------------------------------------
# RetrievalTrace — full pipeline visibility for a single query
# ---------------------------------------------------------------------------

class ChunkSummary(BaseModel):
    """Compact representation of a chunk for trace output."""
    chunk_id: str
    text_preview: str  # first 200 chars
    score: float
    rerank_score: float
    anchor: dict[str, Any]


class RetrievalTrace(BaseModel):
    """Complete step-by-step trace of the retrieval pipeline for one query.

    Intended for developer inspection — not returned in normal chat/study API
    responses.  Exposes raw_chunks (pre-rerank), reranked_chunks, the final
    evidence_pack, and any chunks that were discarded by dedup/truncation.
    """
    query: str
    course_id: str
    action: str
    raw_chunks: list[ChunkSummary]
    """Chunks as returned by ChromaDB, before reranking."""
    reranked_chunks: list[ChunkSummary]
    """Chunks after cross-encoder reranking (same set, different order/scores)."""
    evidence_pack: EvidencePack
    """Final evidence pack after dedup, boost, and token truncation."""
    discarded_chunks: list[ChunkSummary]
    """Chunks present in reranked_chunks but absent from evidence_pack.chunks."""


class RetrievalTestRequest(BaseModel):
    query: str
    course_id: str
    action: str = "explain"


def _to_chunk_summary(chunk) -> ChunkSummary:  # type: ignore[no-untyped-def]
    return ChunkSummary(
        chunk_id=chunk.chunk_id,
        text_preview=chunk.text[:200],
        score=chunk.score,
        rerank_score=chunk.rerank_score,
        anchor=chunk.anchor.model_dump(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/documents/{doc_id}/chunks")
def get_document_chunks(
    doc_id: str = PathParam(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    doc = document_repo.get_by_id(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.sample_chunks_json:
        try:
            return json.loads(doc.sample_chunks_json)
        except json.JSONDecodeError:
            pass
    return []


@router.get("/documents/{doc_id}/parsed")
def get_parsed_output(
    doc_id: str = PathParam(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    doc = document_repo.get_by_id(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    sections = []
    if doc.sections_json:
        try:
            sections = json.loads(doc.sections_json)
        except json.JSONDecodeError:
            pass

    return {
        "id": doc.id,
        "filename": doc.filename,
        "parser_used": doc.parser_used,
        "page_count": doc.page_count,
        "extracted_text_preview": doc.extracted_text_preview,
        "sections": sections[:3],
    }


@router.post("/courses/{course_id}/retrieval")
def test_retrieval(
    course_id: str = PathParam(...),
    query: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    from app.services import retrieval_service

    chunks = retrieval_service.search(query, course_id, top_k=top_k)
    return {
        "query": query,
        "course_id": course_id,
        "total": len(chunks),
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "text": c.text[:300],
                "score": c.score,
                "anchor": c.anchor.model_dump(),
            }
            for c in chunks
        ],
    }


@router.get("/courses/{course_id}/evidence")
def get_evidence_pack(
    course_id: str = PathParam(...),
    query: str = Query(..., min_length=1),
    action: str = Query(default="explain"),
) -> EvidencePack:
    return evidence_pack_service.build(query, action, course_id)


@router.post(
    "/retrieval/test",
    response_model=RetrievalTrace,
    summary="Full retrieval pipeline trace (no LLM generation)",
    description=(
        "Runs retrieval → reranking → evidence pack for the given query and returns "
        "a complete step-by-step trace.  Useful for diagnosing retrieval quality "
        "without invoking the LLM."
    ),
)
def test_retrieval_trace(body: RetrievalTestRequest) -> RetrievalTrace:
    """Return a full RetrievalTrace for inspection — no LLM call."""
    from app.services import retrieval_service
    from app.services import reranker as reranker_module

    # Retrieve with no min_score filter so the trace shows all raw candidates
    raw = retrieval_service.search(
        body.query, body.course_id, top_k=20, min_score=0.0
    )

    # Rerank (cross-encoder if available, else noop)
    reranked = reranker_module.rerank(body.query, raw)

    # Build evidence pack (applies dedup, boost, token truncation)
    pack = evidence_pack_service.build_from_chunks(body.query, body.action, reranked)

    pack_ids = {c.chunk_id for c in pack.chunks}
    discarded = [c for c in reranked if c.chunk_id not in pack_ids]

    return RetrievalTrace(
        query=body.query,
        course_id=body.course_id,
        action=body.action,
        raw_chunks=[_to_chunk_summary(c) for c in raw],
        reranked_chunks=[_to_chunk_summary(c) for c in reranked],
        evidence_pack=pack,
        discarded_chunks=[_to_chunk_summary(c) for c in discarded],
    )


@router.get("/pipeline/health")
def pipeline_health() -> dict[str, Any]:
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=_CHROMA_DB_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collections = client.list_collections()
        collection_sizes = {}
        for col in collections:
            try:
                collection_sizes[col.name] = client.get_collection(col.name).count()
            except Exception:
                collection_sizes[col.name] = -1
        chroma_status = "ok"
    except Exception as exc:
        collection_sizes = {}
        chroma_status = f"error: {exc}"

    uploads_dir = _SERVICES_AI / "uploads"
    uploads_size_mb = 0.0
    if uploads_dir.exists():
        uploads_size_mb = round(
            sum(f.stat().st_size for f in uploads_dir.rglob("*") if f.is_file()) / 1024 / 1024,
            2,
        )

    return {
        "chroma_status": chroma_status,
        "collection_sizes": collection_sizes,
        "uploads_dir_size_mb": uploads_size_mb,
        "python_version": sys.version,
        "chroma_db_path": _CHROMA_DB_PATH,
    }
