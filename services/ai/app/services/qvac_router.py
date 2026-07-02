"""Routes each inference task to a rung on the inference ladder
(docs/agent-memory-plan.md § Principio guida: inference ladder).

Only one QVAC worker is deployed today — a single Qwen3-4B model behind
QVAC_SERVICE_URL (see workers/qvac-service/src/models.js) — so
QVAC_LOCAL_URL and QVAC_SERVER_URL both default to it and every task_type
below resolves to the same endpoint. The table exists so call sites already
tag requests by task_type now; once a distinct local/server deploy exists,
only this module's defaults change, not the callers.

gradino 0/1 (DB / semantic cache) never reach this module — those are served
straight from the DB/cache by the caller before any QVAC call is made.
"""
from dataclasses import dataclass
from typing import Dict, Tuple

from app.core.config import settings
from app.services.hardware_tier import detect_tier

# hardware tier -> model used for "local" task_types. Tier D has no usable
# local model (thin client): local task_types fall back to the server.
TIER_MODEL: Dict[str, str] = {
    "A": "qwen3-14b",
    "B": "qwen3-8b",
    "C": "qwen3-4b-instruct-2507",
    "D": "",
}

SERVER_MODEL = "qwen3-30b-a3b-instruct-2507"

# task_type -> (target, model). model is "" for "local" entries because the
# actual model depends on the caller's hardware tier, resolved in resolve().
LADDER_ROUTING: Dict[str, Tuple[str, str]] = {
    "chat_fast": ("local", ""),
    "chat_agent": ("local", ""),
    "distill": ("server", SERVER_MODEL),
    "map": ("server", SERVER_MODEL),
    "reduce": ("server", SERVER_MODEL),
    "content_gen": ("server", SERVER_MODEL),
    "judge": ("server", SERVER_MODEL),
    "precompute": ("server", SERVER_MODEL),
}


@dataclass(frozen=True)
class Route:
    task_type: str
    target: str  # "local" | "server"
    base_url: str
    model: str


def _server_route(task_type: str, model: str = SERVER_MODEL) -> Route:
    return Route(task_type=task_type, target="server", base_url=settings.QVAC_SERVER_URL, model=model)


def resolve(task_type: str) -> Route:
    """Resolve *task_type* to a concrete endpoint + model.

    Unknown task_types and tier-D "local" task_types both fall back to the
    server route — fail toward the more capable, always-available tier
    rather than guessing a local model that isn't there.
    """
    entry = LADDER_ROUTING.get(task_type)
    if entry is None:
        return _server_route(task_type)

    target, model = entry
    if target != "local":
        return _server_route(task_type, model)

    tier_model = TIER_MODEL[detect_tier()]
    if not tier_model:
        return _server_route(task_type)
    return Route(task_type=task_type, target="local", base_url=settings.QVAC_LOCAL_URL, model=tier_model)
