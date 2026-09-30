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
