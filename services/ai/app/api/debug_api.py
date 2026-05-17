"""Debug API — internal visibility endpoints, active only when DEBUG_MODE=true."""
import json
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import document_repo
from app.schemas.evidence_pack import EvidenceChunk, EvidencePack
from app.services import evidence_pack_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["Debug"])

_HERE = Path(__file__).resolve()
_SERVICES_AI = _HERE.parents[2]


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
    """Complete step-by-step trace of the retrieval pipeline for one query."""
    query: str
    course_id: str
    action: str
    raw_chunks: list[ChunkSummary]
    reranked_chunks: list[ChunkSummary]
    evidence_pack: EvidencePack
    discarded_chunks: list[ChunkSummary]


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


def _bm25_to_chunks(query: str, course_id: str, top_k: int) -> list[EvidenceChunk]:
    """Convert BM25 hits to EvidenceChunk list via rrf_fuse with no dense input."""
    from app.services.hybrid_search import bm25_search, load_bm25_index, rrf_fuse  # noqa: PLC0415

    hits = bm25_search(query, course_id, top_k=top_k)
    if not hits:
        return []
    index_data = load_bm25_index(course_id)
    corpus = index_data[2] if index_data else {}
    return rrf_fuse([], hits, corpus, top_k=top_k)


@router.post("/courses/{course_id}/retrieval")
def test_retrieval(
    course_id: str = PathParam(...),
    query: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    chunks = _bm25_to_chunks(query, course_id, top_k)
    return {
        "query": query,
        "course_id": course_id,
        "total": len(chunks),
        "note": "BM25 sparse retrieval only. QVAC service required for dense+hybrid retrieval.",
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
    candidates = _bm25_to_chunks(query, course_id, top_k=10)
    return evidence_pack_service.build_from_chunks(query, action, candidates)


@router.post(
    "/retrieval/test",
    response_model=RetrievalTrace,
    summary="Full retrieval pipeline trace (no LLM generation)",
    description=(
        "Runs BM25 retrieval → reranking → evidence pack for the given query and returns "
        "a complete step-by-step trace. Start QVAC for dense retrieval."
    ),
)
def test_retrieval_trace(body: RetrievalTestRequest) -> RetrievalTrace:
    """Return a full RetrievalTrace for inspection — no LLM call."""
    from app.services import reranker as reranker_module  # noqa: PLC0415

    raw = _bm25_to_chunks(body.query, body.course_id, top_k=20)
    reranked = reranker_module.rerank(body.query, raw)
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
    from app.services.hybrid_search import _QVAC_INGEST_DIR  # noqa: PLC0415

    bm25_indexes: list[str] = []
    if _QVAC_INGEST_DIR.exists():
        bm25_indexes = [
            f.stem.replace("_bm25", "")
            for f in _QVAC_INGEST_DIR.glob("*_bm25.pkl")
        ]

    uploads_dir = _SERVICES_AI / "uploads"
    uploads_size_mb = 0.0
    if uploads_dir.exists():
        uploads_size_mb = round(
            sum(f.stat().st_size for f in uploads_dir.rglob("*") if f.is_file()) / 1024 / 1024,
            2,
        )

    return {
        "bm25_indexes": bm25_indexes,
        "uploads_dir_size_mb": uploads_size_mb,
        "python_version": sys.version,
    }
