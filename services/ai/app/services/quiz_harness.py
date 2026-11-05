"""Agent harness for quiz generation — plan -> generate -> critique -> repair.

See docs/superpowers/specs/2026-11-05-quiz-agent-harness-design.md.
"""
import logging
from typing import Any, Dict, List, Optional

from app.services.qvac_structured import StructuredGenerationError, generate_json

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


GENERATE_PROMPT_VERSION = "v1"

_GENERATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["prompt", "options", "correct_key", "concept_tag", "difficulty"],
    "properties": {
        "prompt": {"type": "string"},
        "options": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {
                "type": "object",
                "required": ["key", "text"],
                "properties": {
                    "key": {"type": "string", "enum": ["A", "B", "C", "D"]},
                    "text": {"type": "string"},
                },
            },
        },
        "correct_key": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "concept_tag": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
    },
}

_GENERATE_SYSTEM = (
    "You are an expert educator at BitPolito Academy creating one assessment question "
    "from a single source passage.\n"
    "RULES:\n"
    "1. The question must test the cognitive level given in the task (recall / application "
    "/ analysis), based ONLY on the provided passage.\n"
    "2. All 4 options (A-D) must be plausible — wrong options should be conceptually close "
    "but demonstrably wrong from the passage.\n"
    "3. Exactly one option must be correct and directly supported by the passage.\n"
    "4. Use exact technical terminology from the passage.\n"
    "5. concept_tag: a short kebab-case slug for the concept tested.\n"
    "6. difficulty: beginner / intermediate / advanced."
)


async def _generate_one(
    target: PlanTarget,
    context_items: List[Dict[str, str]],
    *,
    feedback: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Generate one question for target, scoped to its single source chunk.

    Returns None (rather than propagating) on StructuredGenerationError, so the
    caller can treat a failed target as needing repair or being dropped.
    LlmDisabledError is not caught here and propagates to abort the run.
    """
    item = next(
        (ci for ci in context_items if ci["chunk_id"] == target["chunk_id"]),
        None,
    )
    context = [item] if item is not None else []

    prompt = (
        f"Write one {target['cognitive_level']}-level multiple-choice question from the "
        "provided passage."
    )
    if feedback:
        prompt += f"\nNote: the previous attempt was rejected — {feedback}"

    try:
        result = await generate_json(
            prompt,
            _GENERATE_SCHEMA,
            context=context,
            system_prompt=_GENERATE_SYSTEM,
            generation_params={"temp": 0.3},
            task_type="content_gen",
        )
    except StructuredGenerationError:
        return None

    return {**result, "chunk_id": target["chunk_id"]}
