"""Debug API — internal visibility endpoints, active only when DEBUG_MODE=true."""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
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
