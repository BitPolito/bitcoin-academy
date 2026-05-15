"""Semantic query cache — deduplicate repeated student questions via Redis.

Embeddings are computed with fastembed (already a dependency, CPU-only).
Cache hits skip the full retrieval + rerank + LLM cycle.

Opt-out: RAG_SEMANTIC_CACHE=false  (default: enabled when REDIS_URL is set)
Similarity threshold: RAG_CACHE_THRESHOLD  (default 0.92)
TTL: RAG_CACHE_TTL_SECONDS  (default 86400 = 24 h)
"""
import hashlib
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("RAG_SEMANTIC_CACHE", "true").lower() in ("true", "1", "yes")
_THRESHOLD = float(os.getenv("RAG_CACHE_THRESHOLD", "0.92"))
_TTL = int(os.getenv("RAG_CACHE_TTL_SECONDS", "86400"))
_REDIS_URL = os.getenv("REDIS_URL", "")
_MAX_SCAN = int(os.getenv("RAG_CACHE_MAX_SCAN", "200"))

_emb_model = None
_emb_attempted = False


def _get_emb():
    global _emb_model, _emb_attempted
    if _emb_attempted:
        return _emb_model
    _emb_attempted = True
    try:
        from fastembed import TextEmbedding  # noqa: PLC0415
        _emb_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
        logger.debug("Semantic cache: fastembed model loaded")
    except Exception as exc:
        logger.warning("Semantic cache: fastembed unavailable — cache disabled: %s", exc)
    return _emb_model


def _embed(text: str) -> Optional[list[float]]:
    model = _get_emb()
    if model is None:
        return None
    try:
        vecs = list(model.embed([text]))
        return vecs[0].tolist()
    except Exception as exc:
        logger.debug("Cache embed failed: %s", exc)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _redis_client():
    if not _REDIS_URL:
        return None
    try:
        import redis  # noqa: PLC0415
        return redis.from_url(_REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.debug("Redis unavailable for semantic cache: %s", exc)
        return None


def _cache_key(course_id: str, vec: list[float]) -> str:
    digest = hashlib.sha1(json.dumps(vec[:8], separators=(',', ':')).encode()).hexdigest()[:12]
    return f"rag:cache:{course_id}:{digest}"


def get_cached(query: str, course_id: str) -> Optional[Any]:
    """Return cached answer dict if a semantically similar query is cached, else None."""
    if not _ENABLED:
        return None
    vec = _embed(query)
    if vec is None:
        return None
    client = _redis_client()
    if client is None:
        return None
    try:
        pattern = f"rag:cache:{course_id}:*"
        keys = client.keys(pattern)
        for key in keys[:_MAX_SCAN]:
            raw = client.get(key)
            if not raw:
                continue
            entry = json.loads(raw)
            stored_vec = entry.get("vec")
            if stored_vec is None:
                continue
            sim = _cosine(vec, stored_vec)
            if sim >= _THRESHOLD:
                logger.info("Semantic cache HIT (sim=%.3f) for course '%s'", sim, course_id)
                return entry["answer"]
    except Exception as exc:
        logger.debug("Cache lookup error: %s", exc)
    return None


def set_cached(query: str, course_id: str, answer: Any) -> None:
    """Store answer in Redis keyed by query embedding."""
    if not _ENABLED:
        return
    vec = _embed(query)
    if vec is None:
        return
    client = _redis_client()
    if client is None:
        return
    try:
        key = _cache_key(course_id, vec)
        payload = json.dumps({"vec": vec, "answer": answer}, separators=(',', ':'))
        client.set(key, payload, ex=_TTL)
        logger.debug("Semantic cache SET for course '%s' (TTL=%ds)", course_id, _TTL)
    except Exception as exc:
        logger.debug("Cache store error: %s", exc)
