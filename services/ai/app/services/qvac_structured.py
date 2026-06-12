"""Client for QVAC /generate_json — schema-validated JSON from the local LLM.

The Node worker enforces the schema (extraction + validation + correction
retries on the model side); this client adds transport-level resilience:
exponential backoff on connection errors and 5xx, typed exceptions for the
two non-retryable outcomes (LLM disabled, schema never satisfied).

Used by the course builder (outline generation, lesson metadata, groundedness
judge) — anywhere a study feature needs structured output instead of prose.
"""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")

# Generation client mirrors study_service: long read timeout for Qwen3-4B on
# CPU; /generate_json may run up to 3 model passes (1 + 2 correction rounds).
_client = httpx.AsyncClient(
    base_url=_QVAC_SERVICE_URL,
    timeout=httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0),
)

_TRANSPORT_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


class LlmDisabledError(RuntimeError):
    """QVAC is running in retrieval-only mode (QVAC_LLM_ENABLED=false)."""


class StructuredGenerationError(RuntimeError):
    """The model could not produce schema-valid JSON after worker-side retries."""

    def __init__(self, message: str, errors: Optional[List[str]] = None, raw: str = ""):
        super().__init__(message)
        self.errors = errors or []
        self.raw = raw


async def generate_json(
    prompt: str,
    schema: Dict[str, Any],
    *,
    context: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None,
    max_retries: Optional[int] = None,
    generation_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a JSON value guaranteed to validate against *schema*.

    context items follow the /generate convention: {"label": str, "text": str}.
    Raises LlmDisabledError, StructuredGenerationError, or httpx errors when
    the worker stays unreachable after transport retries.
    """
    payload: Dict[str, Any] = {"prompt": prompt, "schema": schema}
    if context:
        payload["context"] = context
    if system_prompt:
        payload["systemPrompt"] = system_prompt
    if max_retries is not None:
        payload["maxRetries"] = max_retries
    if generation_params:
        payload["generationParams"] = generation_params

    last_exc: Optional[Exception] = None
    for attempt in range(1, _TRANSPORT_RETRIES + 1):
        try:
            resp = await _client.post("/generate_json", json=payload)
        except httpx.TransportError as exc:
            last_exc = exc
            logger.warning(
                "QVAC /generate_json transport error (attempt %d/%d): %s",
                attempt, _TRANSPORT_RETRIES, exc,
            )
            if attempt < _TRANSPORT_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
            continue

        if resp.status_code == 503:
            raise LlmDisabledError(resp.json().get("error", "LLM disabled"))
        if resp.status_code == 422:
            body = resp.json()
            raise StructuredGenerationError(
                body.get("error", "schema validation failed"),
                errors=body.get("errors"),
                raw=body.get("raw", ""),
            )
        if resp.status_code >= 500:
            last_exc = httpx.HTTPStatusError(
                f"QVAC /generate_json returned {resp.status_code}",
                request=resp.request, response=resp,
            )
            logger.warning(
                "QVAC /generate_json server error %d (attempt %d/%d)",
                resp.status_code, attempt, _TRANSPORT_RETRIES,
            )
            if attempt < _TRANSPORT_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
            continue

        resp.raise_for_status()
        body = resp.json()
        if attempt > 1:
            logger.info("QVAC /generate_json succeeded on transport attempt %d", attempt)
        return body["json"]

    assert last_exc is not None
    raise last_exc
