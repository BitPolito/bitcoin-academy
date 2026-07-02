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


# ---------------------------------------------------------------------------
# task_type routing (docs/agent-memory-plan.md, Fase 0)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_type_none_uses_default_client():
    """Omitting task_type must keep hitting the default client unchanged —
    the behavior every existing caller (course builder, quizzes) relies on."""
    post = AsyncMock(return_value=_response(200, {"json": {"answer": "ok"}, "attempts": 1}))
    with patch.object(qvac_structured._client, "post", post):
        result = await generate_json("say ok", SCHEMA, task_type=None)
    assert result == {"answer": "ok"}
    post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_type_routes_via_qvac_router():
    """A task_type resolving to a different base_url must hit that base_url's
    client, not the default one."""
    from app.services import qvac_router

    fake_route = qvac_router.Route(
        task_type="judge", target="server", base_url="http://server-worker:9000", model="qwen3-30b-a3b-instruct-2507",
    )
    post = AsyncMock(return_value=_response(200, {"json": {"answer": "ok"}, "attempts": 1}))
    default_post = AsyncMock()
    with patch.object(qvac_router, "resolve", return_value=fake_route), \
         patch.object(qvac_structured, "_client_for", return_value=type("C", (), {"post": post})()), \
         patch.object(qvac_structured._client, "post", default_post):
        result = await generate_json("judge this", SCHEMA, task_type="judge")
    assert result == {"answer": "ok"}
    post.assert_awaited_once()
    default_post.assert_not_called()
    payload = post.await_args.kwargs["json"]
    assert payload["model"] == "qwen3-30b-a3b-instruct-2507"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_type_resolves_off_the_event_loop_thread():
    """qvac_router.resolve() must run via asyncio.to_thread — a synchronous
    hardware_tier.detect_tier() cache-miss (nvidia-smi subprocess) must not
    block the event loop for other in-flight requests."""
    from app.services import qvac_router

    fake_route = qvac_router.Route(
        task_type="chat_fast", target="local", base_url="http://local-worker:9000", model="qwen3-8b",
    )
    post = AsyncMock(return_value=_response(200, {"json": {}, "attempts": 1}))
    with patch("app.services.qvac_structured.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread, \
         patch.object(qvac_structured, "_client_for", return_value=type("C", (), {"post": post})()):
        mock_to_thread.return_value = fake_route
        await generate_json("x", SCHEMA, task_type="chat_fast")
    mock_to_thread.assert_awaited_once_with(qvac_router.resolve, "chat_fast")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_type_none_omits_model_from_payload():
    post = AsyncMock(return_value=_response(200, {"json": {}, "attempts": 1}))
    with patch.object(qvac_structured._client, "post", post):
        await generate_json("x", SCHEMA, task_type=None)
    payload = post.await_args.kwargs["json"]
    assert "model" not in payload


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_type_matching_default_url_reuses_default_client():
    """When qvac_router resolves to the same base_url as the default deploy
    (today's reality — only one QVAC worker exists), no second client should
    be created; _client_for must hand back the shared _client."""
    client = qvac_structured._client_for(qvac_structured._QVAC_SERVICE_URL)
    assert client is qvac_structured._client
