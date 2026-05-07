"""ARQ worker — job definitions and WorkerSettings for document ingestion."""
import asyncio
import os

from arq.connections import RedisSettings

from app.workers import pipeline


async def ingest_document(
    ctx,
    document_id: str,
    course_id: str,
    filename: str,
    file_path: str,
    material_type: str = "lecture",
) -> None:
    """ARQ job: parse → chunk → JSONL → QVAC. Timeout 600s, max_tries 2."""
    await asyncio.to_thread(
        pipeline.run,
        document_id=document_id,
        course_id=course_id,
        filename=filename,
        file_path=file_path,
        material_type=material_type,
    )


async def reindex_document_qvac(ctx, document_id: str, course_id: str) -> None:
    """ARQ job: retry QVAC ingest for a document with indexing_status=qvac_pending."""
    await asyncio.to_thread(
        pipeline.reindex_qvac,
        document_id=document_id,
        course_id=course_id,
    )


class WorkerSettings:
    functions = [ingest_document, reindex_document_qvac]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    job_timeout = 600
    max_tries = 2
    retry_delay = 30
