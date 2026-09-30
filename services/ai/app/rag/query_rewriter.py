"""Query rewriting and HyDE for retrieval on ambiguous student questions.

Both techniques call QVAC /generate (local LLM via QVAC SDK) — no external API.

  RAG_QUERY_REWRITE=true
    Rephrases the raw question into a dense information-retrieval query:
    removes hedging, expands acronyms, makes implicit subjects explicit.

  RAG_HYDE=true
    Hypothetical Document Embeddings (Gao et al., 2022):
    generates a short hypothetical passage that would answer the query,
    then uses THAT passage as the retrieval query. Because the hypothetical
    document sits in the same embedding space as real answer passages, it
    yields closer neighbours than the raw question embedding.

HyDE takes precedence when both flags are set. Both fall back to the
original query when the LLM is unavailable or the call fails.
Requires QVAC_LLM_ENABLED=true (the QVAC server must have an LLM loaded).
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_REWRITE_ENABLED = os.getenv("RAG_QUERY_REWRITE", "").lower() in ("true", "1", "yes")
_HYDE_ENABLED = os.getenv("RAG_HYDE", "true").lower() not in ("false", "0", "no")
_QVAC_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
_QVAC_LLM_ENABLED = os.getenv("QVAC_LLM_ENABLED", "true").lower() != "false"
_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

_REWRITE_SYSTEM_PROMPT = (
    "Rewrite the following student question into a concise, precise information-retrieval query. "
    "Rules: remove hedging phrases; expand abbreviations; make implicit subjects explicit; "
    "keep technical terminology unchanged. "
    "Return ONLY the rewritten query — no explanations."
)

_HYDE_SYSTEM_PROMPT = (
    "You are a Bitcoin and blockchain textbook author. "
    "Write a concise factual passage (3–5 sentences) that directly answers the question. "
    "Use precise technical language and include relevant concepts, definitions, or mechanisms. "
    "Write as a paragraph of continuous prose — no bullet points, no headers."
)

# QVAC fallback string when no LLM is loaded — used to detect no-op responses.
_QVAC_NO_LLM_FALLBACK = "Nessun contesto disponibile."


def _is_enabled() -> bool:
    return (_REWRITE_ENABLED or _HYDE_ENABLED) and _QVAC_LLM_ENABLED and bool(_QVAC_URL)


async def _call_qvac(system_prompt: str, question: str) -> Optional[str]:
    """POST to QVAC /generate with no retrieval context (pure LLM completion)."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_QVAC_URL}/generate",
                json={
                    "question": question,
                    "context": [],
                    "systemPrompt": system_prompt,
                },
            )
            resp.raise_for_status()
            answer: str = resp.json().get("answer", "").strip()
            # Reject QVAC's no-LLM fallback string.
            if not answer or answer == _QVAC_NO_LLM_FALLBACK:
                return None
            return answer
    except Exception as exc:
        logger.debug("QVAC query expansion call failed: %s", exc)
        return None


async def expand_query(query: str) -> str:
    """Return the best retrieval string derived from *query*.

    Evaluation order:
      1. HyDE  — if RAG_HYDE=true, generate a hypothetical answer passage.
      2. Rewrite — if RAG_QUERY_REWRITE=true, rephrase for vector search.
      3. Original — always-safe fallback.

    The returned string is used as the retrieval query only; the original
    *query* is still used for generation prompts and citation display.
    """
    if not _is_enabled():
        return query

    if _HYDE_ENABLED:
        expanded = await _call_qvac(_HYDE_SYSTEM_PROMPT, query)
        if expanded:
            logger.debug(
                "HyDE expansion applied: %d chars → %d chars",
                len(query), len(expanded),
            )
            return expanded

    if _REWRITE_ENABLED:
        rewritten = await _call_qvac(_REWRITE_SYSTEM_PROMPT, query)
        if rewritten:
            logger.debug("Query rewrite: %r → %r", query, rewritten)
            return rewritten

    return query
