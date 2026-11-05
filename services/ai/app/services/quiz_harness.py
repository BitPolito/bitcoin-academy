"""Agent harness for quiz generation — plan -> generate -> critique -> repair.

See docs/superpowers/specs/2026-11-05-quiz-agent-harness-design.md.
"""
import logging
from typing import Any, Dict, List, Optional

from app.services.qvac_structured import LlmDisabledError, StructuredGenerationError, generate_json

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
    caller can treat a failed target as needing repair or being dropped. The
    same applies if target["chunk_id"] does not match any context_items entry:
    we must not fall back to a context-free generate_json call, since that
    would silently produce an ungrounded question while still being tagged
    with target["chunk_id"] on the way out.
    LlmDisabledError is not caught here and propagates to abort the run.
    """
    item = next(
        (ci for ci in context_items if ci["chunk_id"] == target["chunk_id"]),
        None,
    )
    if item is None:
        return None
    context = [item]

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


CritiqueVerdict = Dict[str, Any]

CRITIQUE_PROMPT_VERSION = "v1"

_CRITIQUE_CRITERIA = (
    "entailed", "distractors_plausible", "single_defensible", "requires_course_material",
)
# "duplicate" is tracked separately — it's the one criterion where True is the failure, not False.

_CRITIQUE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["entailed", "distractors_plausible", "single_defensible",
                 "requires_course_material", "duplicate"],
    "properties": {
        "entailed": {"type": "boolean"},
        "distractors_plausible": {"type": "boolean"},
        "single_defensible": {"type": "boolean"},
        "requires_course_material": {"type": "boolean"},
        "duplicate": {"type": "boolean"},
    },
}

_CRITIQUE_SYSTEM = (
    "You are a critic judging one multiple-choice question against its source passage and "
    "the other questions already accepted into this quiz.\n"
    "entailed: the correct answer is directly supported by the passage.\n"
    "distractors_plausible: every wrong option is plausible but demonstrably wrong from the "
    "passage — not absurd, not another correct answer.\n"
    "single_defensible: exactly one option is correct; no other option could also be "
    "defended as correct.\n"
    "requires_course_material: the question cannot be answered from general knowledge alone.\n"
    "duplicate: true if this question tests the same fact as one of the other questions shown."
)


async def _critique_one(
    question: Dict[str, Any], source_text: str, accepted_questions: List[Dict[str, Any]],
) -> CritiqueVerdict:
    """Judge one generated question against the five quality criteria.

    Fails closed: if the critic is unavailable (LlmDisabledError) or returns
    an unparsable response (StructuredGenerationError), the question is
    treated as a failure, not a pass — it is never silently accepted just
    because we could not critique it. Mirrors
    lesson_service._judge_groundedness's fail-closed pattern.
    """
    accepted_prompts = [q["prompt"] for q in accepted_questions]
    prompt = (
        f"Question: {question['prompt']}\n"
        f"Options: {question['options']}\n"
        f"Correct key: {question['correct_key']}\n"
        f"Other questions already accepted into this quiz: {accepted_prompts}"
    )

    try:
        result = await generate_json(
            prompt,
            _CRITIQUE_SCHEMA,
            context=[{"label": "source", "text": source_text}],
            system_prompt=_CRITIQUE_SYSTEM,
            generation_params={"temp": 0.1},
            task_type="quiz_critique",
        )
    except (LlmDisabledError, StructuredGenerationError):
        return {"passed": False, "failed_criteria": ["critic unavailable"]}

    failed_criteria = [name for name in _CRITIQUE_CRITERIA if not result.get(name, False)]
    if result.get("duplicate", True):
        failed_criteria.append("duplicate")

    return {"passed": not failed_criteria, "failed_criteria": failed_criteria}


HarnessResult = Dict[str, Any]

DEFAULT_TARGET_COUNT = 4


def _source_text_for(target: PlanTarget, context_items: List[Dict[str, str]]) -> str:
    item = next(
        (ci for ci in context_items if ci["chunk_id"] == target["chunk_id"]),
        None,
    )
    return item["text"] if item is not None else ""


async def run(
    topic: str,
    context_items: List[Dict[str, str]],
    target_count: int = DEFAULT_TARGET_COUNT,
) -> HarnessResult:
    """Run the plan -> generate -> critique -> repair harness.

    Produces at most `target_count` questions, each one passing through at
    most two generate+critique rounds (an initial attempt and, on a failed
    critique, exactly one repair attempt built from the critique's
    `failed_criteria`). The call budget is therefore bounded by
    `4 * target_count + 1` (plan, plus up to generate+critique twice per
    target) — see `trace["calls_budget"]`.

    A `None` generation result (an unresolvable chunk_id, a schema error, or
    the LLM being disabled mid-run) is not retried: the same target and
    context would almost certainly fail the same way again, so the target is
    dropped immediately without spending a repair attempt or a critique call
    on it.

    `LlmDisabledError`/`StructuredGenerationError` at the plan stage end the
    run immediately with no questions produced, since there is nothing yet to
    degrade to. `topic` is accepted for interface symmetry with
    `generate_quiz_questions` and is not otherwise used here yet.
    """
    trace: Dict[str, Any] = {
        "targets_planned": 0,
        "generated": 0,
        "rejected": [],
        "repaired": 0,
        "final_count": 0,
        "calls_used": 0,
        "calls_budget": 4 * target_count + 1,
    }
    accepted: List[Dict[str, Any]] = []

    try:
        targets = await _plan_targets(context_items, target_count)
        trace["calls_used"] += 1
    except (LlmDisabledError, StructuredGenerationError) as exc:
        trace["calls_used"] += 1
        trace["rejected"].append({"stage": "plan", "reason": str(exc)})
        trace["final_count"] = len(accepted)
        return {"questions": accepted, "trace": trace}

    trace["targets_planned"] = len(targets)

    for target in targets:
        source_text = _source_text_for(target, context_items)

        try:
            question = await _generate_one(target, context_items)
        except LlmDisabledError:
            question = None
        trace["calls_used"] += 1

        if question is None:
            trace["rejected"].append({"question_preview": None, "reasons": ["generation failed"]})
            continue

        trace["generated"] += 1
        verdict = await _critique_one(question, source_text, accepted)
        trace["calls_used"] += 1

        if verdict["passed"]:
            accepted.append(question)
            continue

        # Exactly one repair attempt, informed by the critique's failed_criteria.
        feedback = ", ".join(verdict["failed_criteria"])
        try:
            repaired_question = await _generate_one(target, context_items, feedback=feedback)
        except LlmDisabledError:
            repaired_question = None
        trace["calls_used"] += 1

        if repaired_question is None:
            # A None from a repair generate must not trigger an extra critique call.
            trace["rejected"].append({
                "question_preview": question["prompt"] if question else None,
                "reasons": verdict["failed_criteria"],
            })
            continue

        repaired_verdict = await _critique_one(repaired_question, source_text, accepted)
        trace["calls_used"] += 1

        if repaired_verdict["passed"]:
            accepted.append(repaired_question)
            trace["repaired"] += 1
        else:
            trace["rejected"].append({
                "question_preview": repaired_question["prompt"],
                "reasons": repaired_verdict["failed_criteria"],
            })

    trace["final_count"] = len(accepted)
    return {"questions": accepted, "trace": trace}
