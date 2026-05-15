"""Contextual compression of retrieved passages before LLM generation.

For each passage, calls QVAC /generate with an extraction system prompt to
keep only sentences relevant to the user query. Reduces context window usage
without losing signal.

Opt-in via RAG_COMPRESS_CONTEXT=true (default: disabled).
Requires QVAC_LLM_ENABLED=true (the QVAC server must have an LLM loaded).
Falls back silently to the original passage on any error.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("RAG_COMPRESS_CONTEXT", "true").lower() in ("true", "1", "yes")
_QVAC_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
_QVAC_LLM_ENABLED = os.getenv("QVAC_LLM_ENABLED", "true").lower() != "false"
_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
_MAX_WORKERS = 5

_COMPRESS_SYSTEM_PROMPT = (
    "You are a precise information extractor. "
    "Extract ONLY the sentences or phrases from the given passage that are directly relevant "
    "to answering the question. Do not add, infer, or rephrase — copy verbatim text only. "
    "If nothing in the passage is relevant, output exactly: <not_relevant>"
)


def _is_enabled() -> bool:
    return _ENABLED and _QVAC_LLM_ENABLED and bool(_QVAC_URL)


def _compress_one(query: str, text: str) -> str:
    """Extract query-relevant sentences from *text* via QVAC /generate (synchronous).

    Returns *text* unchanged when QVAC is unavailable, when the LLM has no
    model loaded (returns the fallback string), or when it returns <not_relevant>.
    """
    try:
        resp = httpx.post(
            f"{_QVAC_URL}/generate",
            json={
                "question": query,
                "context": [{"label": "", "text": text}],
                "systemPrompt": _COMPRESS_SYSTEM_PROMPT,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        compressed = resp.json().get("answer", "").strip()
        if not compressed or compressed == "<not_relevant>":
            return text
        logger.debug(
            "Compressed passage: %d → %d chars (%.0f%%)",
            len(text), len(compressed), 100 * len(compressed) / max(len(text), 1),
        )
        return compressed
    except Exception as exc:
        logger.debug("Compression skipped — keeping original: %s", exc)
        return text


def compress_passages(query: str, passages: list[str]) -> list[str]:
    """Return compressed versions of *passages* relevant to *query*.

    Runs in parallel via a thread pool (sync-safe — callable from sync code).
    Returns the original list unchanged when compression is disabled or the
    list is empty.
    """
    if not _is_enabled() or not passages:
        return passages

    results: list[str] = list(passages)
    with ThreadPoolExecutor(max_workers=min(len(passages), _MAX_WORKERS)) as pool:
        future_to_idx = {
            pool.submit(_compress_one, query, p): i
            for i, p in enumerate(passages)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.debug("Compression future failed for passage %d: %s", idx, exc)
    return results
