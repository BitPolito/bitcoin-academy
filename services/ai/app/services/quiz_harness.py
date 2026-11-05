"""Agent harness for quiz generation — plan -> generate -> critique -> repair.

See docs/superpowers/specs/2026-11-05-quiz-agent-harness-design.md.
"""
import logging
from typing import Any, Dict, List

from app.services.qvac_structured import generate_json

logger = logging.getLogger(__name__)

PlanTarget = Dict[str, str]

_COGNITIVE_LEVELS = ("recall", "application", "analysis")

PLAN_PROMPT_VERSION = "v1"

_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["targets"],
    "properties": {
        "targets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["passage_index", "cognitive_level"],
                "properties": {
                    "passage_index": {"type": "integer"},
                    "cognitive_level": {"type": "string", "enum": list(_COGNITIVE_LEVELS)},
                },
            },
        }
    },
}

_PLAN_SYSTEM = (
    "You are planning a quiz. Given numbered source passages, select which passages to "
    "test and at what cognitive level, so coverage spans distinct passages and levels "
    "rather than clustering on one passage.\n"
    "Refer to each passage by the 1-based index shown before it (e.g. passage [2]).\n"
    "cognitive_level: 'recall' (states a fact), 'application' (uses a concept in a new "
    "situation), or 'analysis' (compares or explains relationships between concepts)."
)


async def _plan_targets(context_items: List[Dict[str, str]], target_count: int) -> List[PlanTarget]:
    """Select target_count (chunk_id, cognitive_level) pairs from context_items.

    Always returns exactly target_count targets. An invalid or missing
    passage_index from the model is corrected by round-robin assignment over
    context_items rather than trusted — the model never needs to reproduce a
    chunk_id string correctly.
    """
    prompt = (
        f"Select exactly {target_count} target passages for a quiz out of the "
        f"{len(context_items)} numbered passages provided, each with a cognitive_level."
    )
    result = await generate_json(
        prompt,
        _PLAN_SCHEMA,
        context=context_items,
        system_prompt=_PLAN_SYSTEM,
        generation_params={"temp": 0.2},
        task_type="quiz_plan",
    )

    raw_targets = result.get("targets", [])
    targets: List[PlanTarget] = []

    for i in range(target_count):
        if i < len(raw_targets):
            raw = raw_targets[i]
            idx = raw.get("passage_index")
            level = raw.get("cognitive_level")
        else:
            idx = None
            level = None

        if isinstance(idx, int) and 1 <= idx <= len(context_items):
            chunk_id = context_items[idx - 1]["chunk_id"]
        else:
            chunk_id = context_items[i % len(context_items)]["chunk_id"]

        if level not in _COGNITIVE_LEVELS:
            level = "recall"

        targets.append({"chunk_id": chunk_id, "cognitive_level": level})

    return targets
