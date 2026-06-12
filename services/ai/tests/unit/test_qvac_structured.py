"""Unit tests for app/services/qvac_structured.py.

The httpx client is patched — no QVAC service is contacted. Backoff sleeps
are patched to keep the suite fast.
"""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import qvac_structured
from app.services.qvac_structured import (
    LlmDisabledError,
    StructuredGenerationError,
    generate_json,
)

SCHEMA = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}


def _response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=body,
        request=httpx.Request("POST", "http://localhost:3001/generate_json"),
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_returns_json_on_success():
    post = AsyncMock(return_value=_response(200, {"json": {"answer": "ok"}, "attempts": 1}))
    with patch.object(qvac_structured._client, "post", post):
        result = await generate_json("say ok", SCHEMA)
    assert result == {"answer": "ok"}
    post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_payload_includes_optional_fields():
    post = AsyncMock(return_value=_response(200, {"json": {}, "attempts": 1}))
    with patch.object(qvac_structured._client, "post", post):
        await generate_json(
            "task",
            SCHEMA,
            context=[{"label": "p. 1", "text": "ctx"}],
            system_prompt="be precise",
            max_retries=1,
            generation_params={"temp": 0.0},
        )
    payload = post.await_args.kwargs["json"]
    assert payload["prompt"] == "task"
    assert payload["schema"] == SCHEMA
    assert payload["context"] == [{"label": "p. 1", "text": "ctx"}]
    assert payload["systemPrompt"] == "be precise"
    assert payload["maxRetries"] == 1
    assert payload["generationParams"] == {"temp": 0.0}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_503_raises_llm_disabled():
    post = AsyncMock(return_value=_response(503, {"error": "LLM disabled"}))
    with patch.object(qvac_structured._client, "post", post):
        with pytest.raises(LlmDisabledError):
            await generate_json("x", SCHEMA)
    post.assert_awaited_once()  # not retried


@pytest.mark.asyncio
@pytest.mark.unit
async def test_422_raises_structured_generation_error_with_details():
    body = {"error": "validation failed", "errors": ["$.answer: required"], "raw": "{}"}
    post = AsyncMock(return_value=_response(422, body))
    with patch.object(qvac_structured._client, "post", post):
        with pytest.raises(StructuredGenerationError) as exc_info:
            await generate_json("x", SCHEMA)
    assert exc_info.value.errors == ["$.answer: required"]
    assert exc_info.value.raw == "{}"
    post.assert_awaited_once()  # not retried


@pytest.mark.asyncio
@pytest.mark.unit
async def test_transport_error_is_retried_then_succeeds():
    post = AsyncMock(
        side_effect=[
            httpx.ConnectError("refused"),
            _response(200, {"json": {"answer": "ok"}, "attempts": 1}),
        ]
    )
    with patch.object(qvac_structured._client, "post", post), \
         patch("app.services.qvac_structured.asyncio.sleep", new_callable=AsyncMock):
        result = await generate_json("x", SCHEMA)
    assert result == {"answer": "ok"}
    assert post.await_count == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_5xx_is_retried_then_raises_after_exhaustion():
    post = AsyncMock(return_value=_response(500, {"error": "boom"}))
    with patch.object(qvac_structured._client, "post", post), \
         patch("app.services.qvac_structured.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.HTTPStatusError):
            await generate_json("x", SCHEMA)
    assert post.await_count == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_persistent_transport_error_raises_last_exception():
    post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    with patch.object(qvac_structured._client, "post", post), \
         patch("app.services.qvac_structured.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.ConnectError):
            await generate_json("x", SCHEMA)
    assert post.await_count == 3
