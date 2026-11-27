"""Unit tests for app/services/qvac_router.py — Fase 0."""
from unittest.mock import patch

import pytest

from app.services import qvac_router


@pytest.mark.parametrize("task_type,expected_model", [
    ("distill", qvac_router.SERVER_MODEL),
    ("map", qvac_router.SERVER_MODEL),
    ("reduce", qvac_router.SERVER_MODEL),
    ("content_gen", qvac_router.SERVER_MODEL),
    ("judge", qvac_router.SERVER_MODEL),
    ("precompute", qvac_router.SERVER_MODEL),
    ("quiz_plan", qvac_router.SERVER_MODEL),
    ("quiz_critique", qvac_router.SERVER_MODEL),
])
def test_server_task_types_route_to_server(task_type, expected_model):
    route = qvac_router.resolve(task_type)
    assert route.target == "server"
    assert route.base_url == qvac_router.settings.QVAC_SERVER_URL
    assert route.model == expected_model


@pytest.mark.parametrize("tier,expected_model", [
    ("A", "qwen3-14b"),
    ("B", "qwen3-8b"),
    ("C", "qwen3-4b-instruct-2507"),
])
def test_local_task_types_route_to_local_by_tier(tier, expected_model):
    with patch.object(qvac_router, "detect_tier", return_value=tier):
        route = qvac_router.resolve("chat_fast")
    assert route.target == "local"
    assert route.base_url == qvac_router.settings.QVAC_LOCAL_URL
    assert route.model == expected_model


def test_tier_d_local_task_type_falls_back_to_server():
    with patch.object(qvac_router, "detect_tier", return_value="D"):
        route = qvac_router.resolve("chat_agent")
    assert route.target == "server"
    assert route.base_url == qvac_router.settings.QVAC_SERVER_URL
    assert route.model == qvac_router.SERVER_MODEL


def test_unknown_task_type_falls_back_to_server():
    route = qvac_router.resolve("does_not_exist")
    assert route.target == "server"
    assert route.base_url == qvac_router.settings.QVAC_SERVER_URL
    assert route.model == qvac_router.SERVER_MODEL


def test_default_deploy_resolves_local_and_server_to_same_url():
    # Today only one QVAC worker is deployed — QVAC_LOCAL_URL and
    # QVAC_SERVER_URL both default to QVAC_SERVICE_URL — so local and
    # server routes should be indistinguishable at the base_url level
    # until a distinct deploy sets them apart.
    with patch.object(qvac_router, "detect_tier", return_value="B"):
        local_route = qvac_router.resolve("chat_fast")
    server_route = qvac_router.resolve("judge")
    assert local_route.base_url == server_route.base_url


# ---------------------------------------------------------------------------
# Diverging QVAC_LOCAL_URL / QVAC_SERVER_URL — issue #160
# ---------------------------------------------------------------------------
#
# The whole point of the inference ladder is that a diverging local/server
# deploy actually changes where traffic goes. These tests set the two URLs
# to different values and assert EVERY task_type on the ladder reaches the
# endpoint its (target, tier) combination implies — the correctness property
# that the seven migrated call sites (study_service, chat_service,
# document_service, query_rewriter, compressor, pipeline, main.py's
# /health) all depend on via qvac_router.resolve().

_LOCAL_URL = "http://local-qvac.internal:3001"
_SERVER_URL = "http://server-qvac.internal:3002"


@pytest.fixture
def diverging_urls(monkeypatch):
    monkeypatch.setattr(qvac_router.settings, "QVAC_LOCAL_URL", _LOCAL_URL)
    monkeypatch.setattr(qvac_router.settings, "QVAC_SERVER_URL", _SERVER_URL)


@pytest.mark.parametrize("task_type", [
    "chat_fast", "chat_agent", "retrieval",
])
def test_local_task_types_reach_the_local_endpoint_when_diverging(diverging_urls, task_type):
    with patch.object(qvac_router, "detect_tier", return_value="B"):
        route = qvac_router.resolve(task_type)
    assert route.base_url == _LOCAL_URL
    assert route.base_url != _SERVER_URL


@pytest.mark.parametrize("task_type", [
    "distill", "map", "reduce", "content_gen", "judge",
    "precompute", "quiz_plan", "quiz_critique",
])
def test_server_task_types_reach_the_server_endpoint_when_diverging(diverging_urls, task_type):
    route = qvac_router.resolve(task_type)
    assert route.base_url == _SERVER_URL
    assert route.base_url != _LOCAL_URL


def test_tier_d_local_task_types_fall_back_to_server_when_diverging(diverging_urls):
    with patch.object(qvac_router, "detect_tier", return_value="D"):
        route = qvac_router.resolve("chat_fast")
    assert route.base_url == _SERVER_URL


@pytest.mark.asyncio
async def test_resolve_async_matches_resolve(diverging_urls):
    with patch.object(qvac_router, "detect_tier", return_value="C"):
        sync_route = qvac_router.resolve("chat_fast")
        async_route = await qvac_router.resolve_async("chat_fast")
    assert async_route == sync_route


def test_log_startup_routes_logs_tier_and_every_task_type(diverging_urls):
    # Patch the module logger directly rather than relying on the stdlib
    # logging/caplog machinery, which other tests in the suite can leave in
    # a disabled state (e.g. via alembic's fileConfig) unrelated to the
    # behaviour under test here — see test_quiz_generation.py for the same
    # pattern and rationale.
    with patch.object(qvac_router, "detect_tier", return_value="B"), \
         patch.object(qvac_router, "logger") as mock_logger:
        qvac_router.log_startup_routes()

    logged = " ".join(
        str(call.args) for call in mock_logger.info.call_args_list
    )
    assert "B" in logged
    for task_type in qvac_router.LADDER_ROUTING:
        assert task_type in logged
    assert _LOCAL_URL in logged
    assert _SERVER_URL in logged
