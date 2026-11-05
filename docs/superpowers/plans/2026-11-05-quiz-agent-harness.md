# Quiz Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace quiz generation's single schema-validated `/generate_json` call with a bounded
plan → generate → critique → repair loop, so quiz questions are checked against explicit quality
criteria instead of only being well-formed.

**Architecture:** A new `app/services/quiz_harness.py` module owns the four-stage loop and is
called by `quiz_generation.generate_quiz_questions` (unchanged public signature, delegates
internally). Both existing callers (course builder, study page) feed it through the existing
`context_items` convention, extended with an explicit `chunk_id` key. Persistence
(`quiz_generation.persist_quiz`) is untouched.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, `qvac_structured.generate_json` (async, schema-
validated JSON over HTTP), pytest + `unittest.mock.AsyncMock`.

**Spec:** [`docs/superpowers/specs/2026-11-05-quiz-agent-harness-design.md`](../specs/2026-11-05-quiz-agent-harness-design.md)

## Global Constraints

- Every returned question carries a resolvable `chunk_id` (issue #134 acceptance criterion).
- Hard cap on LLM calls, no unbounded loop — enforced by construction: at most
  `1 (plan) + N (generate) + N (critique) + N (repair-generate) + N (repair-critique) = 4N + 1`
  calls for `N` targets, with exactly one repair round per rejected question.
- Degrade honestly: on `LlmDisabledError`/`StructuredGenerationError`, return fewer questions (or
  none) with a reason in the trace — never raise out of the harness, never return malformed output.
- `generate_json` is always imported and called as `from app.services.qvac_structured import
  generate_json` inside the module that calls it, and tests patch it at that module's path (e.g.
  `app.services.quiz_harness.generate_json`), per the existing convention in
  `quiz_generation.py`/`lesson_service.py`.
- No new background job / `GenerationRun` row for quizzes — stays synchronous, same shape as
  today's `POST /courses/{course_id}/quizzes/generate`.
- No frontend changes in this plan — the `trace` field rides in the existing API response only.

## Review Focus

- Fewer distinct chunks in `context_items` than the target question count — the plan stage must
  reuse chunks (not crash or return fewer targets than requested). Covered in Task 2.
- A critique response missing one of the required boolean fields (worker validated the schema but
  a key check in Python code must not `KeyError`) — use `.get(..., False)` defensively. Covered in
  Task 4.
- Duplicate questions across the same run — the critique call for question *k* must see the
  already-accepted questions 1..k-1 and flag a near-duplicate, not silently accept it. Covered in
  Task 4.
- A repair-stage call (generate or critique) itself raising `LlmDisabledError` mid-run — the run
  must drop that one target and continue/finish rather than propagating the exception out of
  `run()`. Covered in Task 5.
- `target_count` larger than the number of distinct `context_items` entries — round-robin target
  assignment must not raise an `IndexError` and must still produce valid, distinct questions.
  Covered in Task 2 (planning) and Task 5 (full run).

---

## Task 1: Fix `context_items` so every caller's entries carry a `chunk_id`

The study-page caller currently builds `context_items` from `result.citations`
(`{label, text}`), which has no chunk id anywhere on it — only `result.evidence_pack.chunks[i]
.chunk_id` does. The course-builder caller already has a chunk id, just under the `label` key. Both
need an explicit `"chunk_id"` key before the harness (Task 2+) can plan against it.

**Files:**
- Modify: `app/services/lesson_service.py:189-195` (`_load_context`)
- Modify: `app/api/quizzes_api.py:159-172` (`generate_quiz`)
- Test: `tests/unit/test_lesson_service.py:140-151` (`test_load_context_returns_items`)
- Test: `tests/integration/test_quizzes_certificates_api.py:14,38-42,58-105`

**Interfaces:**
- Produces: every `context_items` entry downstream now has keys `{"label": str, "text": str,
  "chunk_id": str}` — this is what Task 2's `_plan_targets` and Task 3's `_generate_one` consume.

- [ ] **Step 1: Write the failing test for `_load_context`**

In `tests/unit/test_lesson_service.py`, extend `test_load_context_returns_items` with:
```python
    assert items[0]["chunk_id"] == "p1"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_lesson_service.py::test_load_context_returns_items -v`
Expected: FAIL — `KeyError: 'chunk_id'`

- [ ] **Step 3: Add `chunk_id` to `_load_context`'s output**

In `app/services/lesson_service.py:193`, change:
```python
            context_items.append({"label": cid, "text": rows[cid].text})
```
to also set `"chunk_id": cid` (same value as `label` here — `label` already doubles as the chunk id
for this caller; this just makes the key explicit and uniform with the study-page caller after
Step 6).

- [ ] **Step 4: Run it to verify it passes**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_lesson_service.py::test_load_context_returns_items -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for `quizzes_api.generate_quiz`'s context_items**

In `tests/integration/test_quizzes_certificates_api.py`, the module-level `_RETRIEVE_RESULT`
currently only sets `citations`. Replace it with a `DispatchResult` that also carries an
`evidence_pack`:
```python
from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk, EvidencePack

_RETRIEVE_RESULT = DispatchResult(
    answer="",
    citations=[SourceChunk(snippet="A UTXO is an unspent transaction output.", score=0.9, label="p1")],
    retrieval_used=True,
    evidence_pack=EvidencePack(
        query="UTXO model basics",
        action="retrieve",
        chunks=[
            EvidenceChunk(
                chunk_id="chunk-1",
                text="A UTXO is an unspent transaction output.",
                score=0.9,
                anchor=CitationAnchor(
                    doc_id="doc-1", doc_name="p1", chunk_id="chunk-1", chunk_type="text",
                ),
            )
        ],
        total_candidates=1,
        ordering=[0],
        deduped_passages=["A UTXO is an unspent transaction output."],
    ),
)
```
Add a new test `test_generate_quiz_uses_evidence_pack_chunk_id` that patches
`app.services.quiz_generation.generate_json` (unchanged patch target for this task — Task 7
switches this to `quiz_harness.generate_json`), asserts the mock's `context` kwarg on its first
call contains a dict with `"chunk_id": "chunk-1"`.

- [ ] **Step 6: Run it to verify it fails**

Run: `cd services/ai && uv run --no-sync pytest tests/integration/test_quizzes_certificates_api.py::TestGenerateQuiz::test_generate_quiz_uses_evidence_pack_chunk_id -v`
Expected: FAIL — context items built from `citations` have no `chunk_id`.

- [ ] **Step 7: Build `context_items` from `result.evidence_pack.chunks` in `quizzes_api.py`**

In `app/api/quizzes_api.py:159-172`, replace the `result.citations`-based comprehension:
```python
    if result.evidence_pack is None or not result.evidence_pack.chunks:
        raise ValidationError_(
            "No source material found for this topic in the course. Try a broader query."
        )

    context_items = [
        {"label": c.anchor.doc_name, "text": c.text, "chunk_id": c.chunk_id}
        for c in result.evidence_pack.chunks
    ]
```
(drops the old `if not context_items: raise ...` check, replaced by the `evidence_pack` guard above
it, since an empty-chunks pack and a `None` pack are now both "no source material").

- [ ] **Step 8: Run it to verify it passes, then run the rest of the quiz integration tests**

Run: `cd services/ai && uv run --no-sync pytest tests/integration/test_quizzes_certificates_api.py -v`
Expected: all PASS, including `test_generate_quiz_422_when_no_source_material` (its
`DispatchResult` has no `evidence_pack` set, so the `None` guard fires) and
`test_generate_quiz_persists_to_db` (uses the now-fixed `_RETRIEVE_RESULT`).

- [ ] **Step 9: Commit**

```bash
git add app/services/lesson_service.py app/api/quizzes_api.py tests/unit/test_lesson_service.py tests/integration/test_quizzes_certificates_api.py
git commit -m "fix(rag): carry chunk_id through quiz context_items for both callers"
```

---

## Task 2: `quiz_harness.py` — plan stage

Selects which passages to test and at what cognitive level, from the evidence already in
`context_items` — no new retrieval call. The model is asked to refer to passages by their 1-based
position (matching the `[N]` convention `generate-json.js`'s `buildContextBlock` already uses), not
by `chunk_id` text, so an invented or out-of-range reference can be corrected deterministically
instead of trusted.

**Files:**
- Create: `app/services/quiz_harness.py`
- Create: `tests/unit/test_quiz_harness.py`
- Modify: `app/services/qvac_router.py:33-42` (`LADDER_ROUTING`)
- Modify: `tests/unit/test_qvac_router.py`

**Interfaces:**
- Consumes: `app.services.qvac_structured.generate_json(prompt, schema, *, context=None,
  system_prompt=None, generation_params=None, task_type=None) -> Dict[str, Any]`;
  `app.services.qvac_structured.LlmDisabledError`, `StructuredGenerationError`.
- Produces: `PlanTarget = Dict[str, str]` with keys `{"chunk_id": str, "cognitive_level": str}`;
  `async def _plan_targets(context_items: List[Dict[str, str]], target_count: int) ->
  List[PlanTarget]` — always returns exactly `target_count` targets (round-robin over
  `context_items` filling in for anything missing/invalid from the model), or raises
  `LlmDisabledError`/`StructuredGenerationError` if the `generate_json` call itself fails. Consumed
  by Task 5's `run()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_quiz_harness.py
import pytest
from unittest.mock import AsyncMock, patch

from app.services.qvac_structured import LlmDisabledError, StructuredGenerationError
from app.services.quiz_harness import _plan_targets

_CONTEXT = [
    {"label": "p1", "text": "UTXO text", "chunk_id": "c1"},
    {"label": "p2", "text": "PoW text", "chunk_id": "c2"},
]


@pytest.mark.asyncio
async def test_plan_targets_maps_passage_index_to_chunk_id():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": [
            {"passage_index": 2, "cognitive_level": "application"},
            {"passage_index": 1, "cognitive_level": "recall"},
        ]}
        targets = await _plan_targets(_CONTEXT, target_count=2)

    assert targets == [
        {"chunk_id": "c2", "cognitive_level": "application"},
        {"chunk_id": "c1", "cognitive_level": "recall"},
    ]


@pytest.mark.asyncio
async def test_plan_targets_corrects_invalid_passage_index():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": [{"passage_index": 99, "cognitive_level": "recall"}]}
        targets = await _plan_targets(_CONTEXT, target_count=1)

    assert targets[0]["chunk_id"] in {"c1", "c2"}


@pytest.mark.asyncio
async def test_plan_targets_pads_when_model_returns_too_few():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": [{"passage_index": 1, "cognitive_level": "recall"}]}
        targets = await _plan_targets(_CONTEXT, target_count=3)

    assert len(targets) == 3


@pytest.mark.asyncio
async def test_plan_targets_reuses_chunks_when_target_count_exceeds_available():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": []}
        targets = await _plan_targets(_CONTEXT, target_count=5)

    assert len(targets) == 5
    assert {t["chunk_id"] for t in targets} == {"c1", "c2"}


@pytest.mark.asyncio
async def test_plan_targets_propagates_llm_disabled():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = LlmDisabledError("disabled")
        with pytest.raises(LlmDisabledError):
            await _plan_targets(_CONTEXT, target_count=1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.quiz_harness'`

- [ ] **Step 3: Create `app/services/quiz_harness.py` with the plan stage**

```python
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
    ...
```

The implementer writes the body: one `generate_json(prompt, _PLAN_SCHEMA, context=context_items,
system_prompt=_PLAN_SYSTEM, generation_params={"temp": 0.2}, task_type="quiz_plan")` call (prompt
text states `target_count` and lists the available passage count), then builds the
`target_count`-length result by walking `result.get("targets", [])`: for each raw target, resolve
`passage_index` to `context_items[idx - 1]["chunk_id"]` when `1 <= idx <= len(context_items)`,
otherwise assign `context_items[i % len(context_items)]["chunk_id"]` (round-robin by position in
the output list); validate `cognitive_level` against `_COGNITIVE_LEVELS`, defaulting to `"recall"`.
Stop once `target_count` targets are collected; if the model returned fewer, keep round-robin-
filling until the count is reached. Let `LlmDisabledError`/`StructuredGenerationError` from
`generate_json` propagate uncaught — Task 5's `run()` catches them at the call site.

- [ ] **Step 4: Run to verify they pass**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -v`
Expected: PASS

- [ ] **Step 5: Register `quiz_plan` in `qvac_router.LADDER_ROUTING`**

In `app/services/qvac_router.py:33-42`, add `"quiz_plan": ("server", SERVER_MODEL),` to the
`LADDER_ROUTING` dict (alongside `"judge"`/`"content_gen"` — explicit registration rather than
relying on the unknown-task_type fallback).

- [ ] **Step 6: Add a parametrize case to `test_qvac_router.py`**

In `tests/unit/test_qvac_router.py`, add `("quiz_plan", qvac_router.SERVER_MODEL)` to the
`test_server_task_types_route_to_server` parametrize list.

- [ ] **Step 7: Run the router tests to verify they pass**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_qvac_router.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/services/quiz_harness.py tests/unit/test_quiz_harness.py app/services/qvac_router.py tests/unit/test_qvac_router.py
git commit -m "feat(rag): add plan stage to the quiz agent harness"
```

---

## Task 3: `quiz_harness.py` — generate stage

One `generate_json` call per target, pinned to that target's single chunk so the model cannot pull
material from elsewhere in the evidence pack. Reuses the `content_gen` task type (same model as
today's quiz generation — no new routing entry needed).

**Files:**
- Modify: `app/services/quiz_harness.py`
- Modify: `tests/unit/test_quiz_harness.py`

**Interfaces:**
- Consumes: `PlanTarget` from Task 2.
- Produces: `async def _generate_one(target: PlanTarget, context_items: List[Dict[str, str]], *,
  feedback: Optional[str] = None) -> Optional[Dict[str, Any]]` — returns a question dict with keys
  `{"prompt", "options", "correct_key", "concept_tag", "difficulty", "chunk_id"}`, or `None` if
  generation failed (`StructuredGenerationError`/`LlmDisabledError` caught here, not propagated —
  the caller treats `None` as "this target needs repair or must be dropped"). Consumed by Task 5's
  `run()` and by Task 4's critique tests (as critique input).

- [ ] **Step 1: Write the failing tests**

```python
_TARGET = {"chunk_id": "c1", "cognitive_level": "recall"}

_QUESTION = {
    "prompt": "What is a UTXO?",
    "options": [
        {"key": "A", "text": "An unspent transaction output"},
        {"key": "B", "text": "A mining reward"},
        {"key": "C", "text": "A block header"},
        {"key": "D", "text": "A wallet address"},
    ],
    "correct_key": "A",
    "concept_tag": "utxo-model",
    "difficulty": "beginner",
}


@pytest.mark.asyncio
async def test_generate_one_attaches_chunk_id():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = dict(_QUESTION)
        question = await _generate_one(_TARGET, _CONTEXT)

    assert question["chunk_id"] == "c1"
    assert question["prompt"] == "What is a UTXO?"


@pytest.mark.asyncio
async def test_generate_one_scopes_context_to_the_target_chunk():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = dict(_QUESTION)
        await _generate_one(_TARGET, _CONTEXT)

    call_context = mock_gj.call_args.kwargs["context"]
    assert call_context == [{"label": "p1", "text": "UTXO text", "chunk_id": "c1"}]


@pytest.mark.asyncio
async def test_generate_one_includes_feedback_in_prompt_when_repairing():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = dict(_QUESTION)
        await _generate_one(_TARGET, _CONTEXT, feedback="rejected: distractors too easy")

    prompt_arg = mock_gj.call_args.args[0]
    assert "rejected: distractors too easy" in prompt_arg


@pytest.mark.asyncio
async def test_generate_one_returns_none_on_structured_generation_error():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = StructuredGenerationError("bad schema")
        question = await _generate_one(_TARGET, _CONTEXT)

    assert question is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -k generate_one -v`
Expected: FAIL — `ImportError: cannot import name '_generate_one'`

- [ ] **Step 3: Implement `_generate_one` in `app/services/quiz_harness.py`**

Add schema/prompt constants:
```python
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
    ...
```

Implementer writes the body: find the single entry in `context_items` whose `"chunk_id"` matches
`target["chunk_id"]` and pass it as `context=[that_item]` (a list of exactly one); build the prompt
from `target["cognitive_level"]` and, when `feedback` is given, append it verbatim (e.g. `f"Note:
the previous attempt was rejected — {feedback}"`); call `generate_json(prompt, _GENERATE_SCHEMA,
context=[item], system_prompt=_GENERATE_SYSTEM, generation_params={"temp": 0.3},
task_type="content_gen")`; on success, return the result dict with `"chunk_id":
target["chunk_id"]` merged in; catch `StructuredGenerationError` and return `None` (do not catch
`LlmDisabledError` — let it propagate, matching the plan stage's contract, since a disabled LLM
should abort the run, not silently drop one target).

- [ ] **Step 4: Run to verify they pass**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -k generate_one -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/quiz_harness.py tests/unit/test_quiz_harness.py
git commit -m "feat(rag): add generate stage to the quiz agent harness"
```

---

## Task 4: `quiz_harness.py` — critique stage

One call per generated question, checking it against the five criteria from issue #134. Fails
closed on an unavailable critic (treated as a failure, not a pass).

**Files:**
- Modify: `app/services/quiz_harness.py`
- Modify: `tests/unit/test_quiz_harness.py`
- Modify: `app/services/qvac_router.py:33-42`
- Modify: `tests/unit/test_qvac_router.py`

**Interfaces:**
- Consumes: a question dict from Task 3's `_generate_one`.
- Produces: `CritiqueVerdict = Dict[str, Any]` with keys `{"passed": bool, "failed_criteria":
  List[str]}`; `async def _critique_one(question: Dict[str, Any], source_text: str,
  accepted_questions: List[Dict[str, Any]]) -> CritiqueVerdict`. Never raises — fails closed.
  Consumed by Task 5's `run()`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_critique_one_passes_when_all_criteria_met():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {
            "entailed": True, "distractors_plausible": True, "single_defensible": True,
            "requires_course_material": True, "duplicate": False,
        }
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict == {"passed": True, "failed_criteria": []}


@pytest.mark.asyncio
async def test_critique_one_reports_each_failed_criterion():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {
            "entailed": False, "distractors_plausible": True, "single_defensible": True,
            "requires_course_material": True, "duplicate": True,
        }
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert set(verdict["failed_criteria"]) == {"entailed", "duplicate"}


@pytest.mark.asyncio
async def test_critique_one_handles_missing_fields_defensively():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"entailed": True}  # worker returned a partial object
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert "distractors_plausible" in verdict["failed_criteria"]


@pytest.mark.asyncio
async def test_critique_one_passes_accepted_questions_as_duplicate_context():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {
            "entailed": True, "distractors_plausible": True, "single_defensible": True,
            "requires_course_material": True, "duplicate": False,
        }
        await _critique_one(_QUESTION, "UTXO text", [{"prompt": "Earlier question?"}])

    prompt_arg = mock_gj.call_args.args[0]
    assert "Earlier question?" in prompt_arg


@pytest.mark.asyncio
async def test_critique_one_fails_closed_on_llm_disabled():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = LlmDisabledError("disabled")
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert verdict["failed_criteria"] == ["critic unavailable"]


@pytest.mark.asyncio
async def test_critique_one_fails_closed_on_structured_generation_error():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = StructuredGenerationError("bad schema")
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert verdict["failed_criteria"] == ["critic unavailable"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -k critique_one -v`
Expected: FAIL — `ImportError: cannot import name '_critique_one'`

- [ ] **Step 3: Implement `_critique_one` in `app/services/quiz_harness.py`**

```python
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
) -> Dict[str, Any]:
    ...
```

Implementer writes the body: build the prompt from `question["prompt"]`/`question["options"]`/
`question["correct_key"]`, the `source_text`, and a listing of `accepted_questions`' `"prompt"`
values (empty-list-safe); call `generate_json(prompt, _CRITIQUE_SCHEMA, context=[{"label":
"source", "text": source_text}], system_prompt=_CRITIQUE_SYSTEM, generation_params={"temp": 0.1},
task_type="quiz_critique")`; read each of `_CRITIQUE_CRITERIA` via `result.get(name, False)`
(missing ⇒ failed, matching Step 1's defensive test) and `duplicate = result.get("duplicate",
True)` (missing ⇒ treated as a duplicate, the safer default); `failed_criteria` is every criterion
in `_CRITIQUE_CRITERIA` whose value is falsy, plus `"duplicate"` if `duplicate` is truthy; `passed
= not failed_criteria`. On `(LlmDisabledError, StructuredGenerationError)`, return `{"passed":
False, "failed_criteria": ["critic unavailable"]}` — fail closed, mirroring
`lesson_service._judge_groundedness`'s pattern in `process_lesson()`.

- [ ] **Step 4: Run to verify they pass**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -k critique_one -v`
Expected: PASS

- [ ] **Step 5: Register `quiz_critique` in `qvac_router.LADDER_ROUTING` and add its router test**

Same as Task 2 Step 5-7: add `"quiz_critique": ("server", SERVER_MODEL),` to `LADDER_ROUTING`, add
`("quiz_critique", qvac_router.SERVER_MODEL)` to `test_server_task_types_route_to_server`'s
parametrize list, run `tests/unit/test_qvac_router.py` to confirm PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/quiz_harness.py tests/unit/test_quiz_harness.py app/services/qvac_router.py tests/unit/test_qvac_router.py
git commit -m "feat(rag): add critique stage to the quiz agent harness"
```

---

## Task 5: `quiz_harness.py` — repair loop and `run()` orchestration

Wires plan → generate → critique together, with exactly one repair attempt per rejected question,
and produces the structured trace.

**Files:**
- Modify: `app/services/quiz_harness.py`
- Modify: `tests/unit/test_quiz_harness.py`

**Interfaces:**
- Consumes: `_plan_targets` (Task 2), `_generate_one` (Task 3), `_critique_one` (Task 4).
- Produces: `DEFAULT_TARGET_COUNT: int = 4`; `HarnessResult = Dict[str, Any]` with keys
  `{"questions": List[Dict[str, Any]], "trace": Dict[str, Any]}`; `trace` has keys
  `{"targets_planned": int, "generated": int, "rejected": List[Dict[str, Any]], "repaired": int,
  "final_count": int, "calls_used": int, "calls_budget": int}`; `async def run(topic: str,
  context_items: List[Dict[str, str]], target_count: int = DEFAULT_TARGET_COUNT) ->
  HarnessResult`. Never raises — `LlmDisabledError` at the plan stage is caught the same as
  `StructuredGenerationError` and turned into a graceful empty `HarnessResult` with a reason in
  the trace, per this plan's own Global Constraints ("never raise out of the harness"). **Correction
  (ruled during Task 5's implementation, see SDD ledger):** an earlier draft of this paragraph said
  `run()` should re-raise `LlmDisabledError` at the plan stage to match
  `generate_quiz_questions`'s pre-harness contract; that contradicted this task's own verbatim
  test (`test_run_llm_disabled_at_plan_stage_returns_no_questions`, which asserts a graceful
  return, not `pytest.raises`) and was an authoring error, not a deliberate choice — the graceful
  path is what's implemented and is correct. Consumed by Task 7's
  `quiz_generation.generate_quiz_questions`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_run_all_pass_returns_every_question_with_no_repairs():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}] * 2
        mock_gen.return_value = dict(_QUESTION)
        mock_crit.return_value = {"passed": True, "failed_criteria": []}

        result = await run("UTXO model", _CONTEXT, target_count=2)

    assert len(result["questions"]) == 2
    assert result["trace"]["repaired"] == 0
    assert result["trace"]["final_count"] == 2
    assert result["trace"]["calls_used"] == 1 + 2 + 2  # plan + 2 generate + 2 critique


@pytest.mark.asyncio
async def test_run_rejected_then_repaired_is_recorded_and_kept():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}]
        mock_gen.return_value = dict(_QUESTION)
        mock_crit.side_effect = [
            {"passed": False, "failed_criteria": ["entailed"]},
            {"passed": True, "failed_criteria": []},
        ]

        result = await run("UTXO model", _CONTEXT, target_count=1)

    assert result["trace"]["repaired"] == 1
    assert len(result["questions"]) == 1
    assert result["trace"]["calls_used"] == 1 + 2 + 2  # plan + (generate+critique) x2


@pytest.mark.asyncio
async def test_run_retry_limit_reached_drops_the_question_with_reasons():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}]
        mock_gen.return_value = dict(_QUESTION)
        mock_crit.return_value = {"passed": False, "failed_criteria": ["entailed"]}

        result = await run("UTXO model", _CONTEXT, target_count=1)

    assert result["questions"] == []
    assert result["trace"]["final_count"] == 0
    assert len(result["trace"]["rejected"]) == 1
    assert result["trace"]["rejected"][0]["reasons"] == ["entailed"]
    # Exactly one repair attempt — no third generate/critique pass.
    assert result["trace"]["calls_used"] == 1 + 2 + 2


@pytest.mark.asyncio
async def test_run_llm_disabled_at_plan_stage_returns_no_questions():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan:
        mock_plan.side_effect = LlmDisabledError("disabled")

        result = await run("UTXO model", _CONTEXT, target_count=2)

    assert result["questions"] == []
    assert result["trace"]["final_count"] == 0


@pytest.mark.asyncio
async def test_run_llm_disabled_mid_generate_drops_that_target_and_continues():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}] * 2
        mock_gen.side_effect = [dict(_QUESTION), None]  # second target's generation failed
        mock_crit.return_value = {"passed": True, "failed_criteria": []}

        result = await run("UTXO model", _CONTEXT, target_count=2)

    assert len(result["questions"]) == 1
    assert len(result["trace"]["rejected"]) == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -k "test_run" -v`
Expected: FAIL — `ImportError: cannot import name 'run'`

- [ ] **Step 3: Implement `run()` in `app/services/quiz_harness.py`**

```python
from app.services.qvac_structured import LlmDisabledError, StructuredGenerationError

DEFAULT_TARGET_COUNT = 4


async def run(
    topic: str, context_items: List[Dict[str, str]], target_count: int = DEFAULT_TARGET_COUNT,
) -> Dict[str, Any]:
    ...
```

Implementer writes the body following the design doc's orchestration exactly: call
`_plan_targets`, catching `LlmDisabledError`/`StructuredGenerationError` from it to end the run
immediately with `{"questions": [], "trace": {..., "rejected": [{"stage": "plan", "reason":
str(exc)}]}}` (**correction, ruled during Task 5** — catch, do not propagate; see the Interfaces
block above); otherwise iterate the returned targets, for each one calling `_generate_one` then (if
it returned a question) `_critique_one` against the already-`accepted` list; on a failed critique,
attempt exactly one repair (`_generate_one(target, context_items, feedback=...)` built from
`failed_criteria`, then `_critique_one` again if the repair generated a
question); a `None` from the *initial* generate call (not the repair attempt) is dropped
immediately with no repair — repair is reserved for a question that generated but failed critique
(**correction, ruled during Task 5** — the verbatim test
`test_run_llm_disabled_mid_generate_drops_that_target_and_continues` requires this: it mocks
exactly 2 `_generate_one` calls for 2 targets, which a repair-on-None path would exceed); append
to `accepted` on any pass, otherwise to `trace["rejected"]` with a
`question_preview` (the rejected question's `"prompt"` if one exists, else `None`) and `"reasons"`;
increment `trace["calls_used"]` once per `_plan_targets`/`_generate_one`/`_critique_one` call
actually made (a `None` from a previous repair generate must not trigger an extra critique call —
track this explicitly so the `calls_used == 1 + 2 + 2` assertions in Step 1 hold); set
`trace["calls_budget"] = 4 * target_count + 1` and `trace["final_count"] = len(accepted)` before
returning. `topic` is accepted for interface symmetry with `generate_quiz_questions` and is not
otherwise used inside `run()` yet — the implementer may thread it into `_generate_one`'s prompt
later if useful, but no test here requires it.

- [ ] **Step 4: Run to verify they pass**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_harness.py -v`
Expected: PASS (every test in the file, not just this task's)

- [ ] **Step 5: Commit**

```bash
git add app/services/quiz_harness.py tests/unit/test_quiz_harness.py
git commit -m "feat(rag): add bounded repair loop and run() orchestrator to the quiz harness"
```

---

## Task 6: Prompt registry wiring

Registers the harness's new prompts so `get_prompt`/`list_prompts` can inspect them, and retires
`quiz_generation.py`'s now-dead multi-question schema/prompt constants (superseded by Task 3's
single-question ones).

**Files:**
- Modify: `app/prompts/registry.py:29-52`
- Modify: `tests/unit/test_prompt_registry.py`

(`app/services/quiz_generation.py`'s now-dead `QUIZ_PROMPT_VERSION`/`QUIZ_SCHEMA`/`QUIZ_SYSTEM`
are deleted in Task 7, once their last caller is rewritten — see that task's rationale.)

**Interfaces:**
- Consumes: `quiz_harness.PLAN_PROMPT_VERSION`, `quiz_harness._PLAN_SYSTEM`,
  `quiz_harness.GENERATE_PROMPT_VERSION`, `quiz_harness._GENERATE_SYSTEM`,
  `quiz_harness.CRITIQUE_PROMPT_VERSION`, `quiz_harness._CRITIQUE_SYSTEM` (all from Tasks 2-4).
- Produces: registry entries `"quiz_plan"`, `"quiz_critique"`; `"quiz_gen"` now mirrors
  `quiz_harness.GENERATE_PROMPT_VERSION`/`_GENERATE_SYSTEM` instead of the deleted
  `quiz_generation.QUIZ_PROMPT_VERSION`/`QUIZ_SYSTEM`.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_prompt_registry.py`, add `"quiz_plan"` and `"quiz_critique"` to
`EXPECTED_NAMES`, and add:
```python
def test_quiz_plan_version_matches_quiz_harness_constant():
    from app.services import quiz_harness
    assert get_prompt("quiz_plan").version == quiz_harness.PLAN_PROMPT_VERSION
    assert get_prompt("quiz_plan").system == quiz_harness._PLAN_SYSTEM


def test_quiz_critique_version_matches_quiz_harness_constant():
    from app.services import quiz_harness
    assert get_prompt("quiz_critique").version == quiz_harness.CRITIQUE_PROMPT_VERSION
    assert get_prompt("quiz_critique").system == quiz_harness._CRITIQUE_SYSTEM
```
Update `test_quiz_gen_version_matches_quiz_generation_constant` to
`test_quiz_gen_version_matches_quiz_harness_constant`, asserting against
`quiz_harness.GENERATE_PROMPT_VERSION`/`_GENERATE_SYSTEM` instead of `quiz_generation`'s deleted
constants.

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_prompt_registry.py -v`
Expected: FAIL — `AssertionError` (names mismatch) and `AttributeError` on the renamed test.

- [ ] **Step 3: Update `_build_registry()` in `app/prompts/registry.py`**

Change the import line to `from app.services import lesson_service, outline_service,
quiz_generation, quiz_harness, study_service` (keep `quiz_generation` — still used by
`persist_quiz` elsewhere, just no longer for the `quiz_gen` prompt). Replace the `"quiz_gen"` entry:
```python
        "quiz_gen": Prompt(
            "quiz_gen", quiz_harness.GENERATE_PROMPT_VERSION, quiz_harness._GENERATE_SYSTEM,
        ),
        "quiz_plan": Prompt(
            "quiz_plan", quiz_harness.PLAN_PROMPT_VERSION, quiz_harness._PLAN_SYSTEM,
        ),
        "quiz_critique": Prompt(
            "quiz_critique", quiz_harness.CRITIQUE_PROMPT_VERSION, quiz_harness._CRITIQUE_SYSTEM,
        ),
```

Leave `quiz_generation.py`'s `QUIZ_PROMPT_VERSION`/`QUIZ_SCHEMA`/`QUIZ_SYSTEM` in place for now —
`generate_quiz_questions` still calls `generate_json` with them until Task 7 rewires it. Deleting
them here would leave the module referencing nothing until Task 7 lands, breaking the "tests pass
after every task" invariant. Task 7 Step 3 deletes them once their last caller is rewritten.

- [ ] **Step 4: Run to verify it passes**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_prompt_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/prompts/registry.py tests/unit/test_prompt_registry.py
git commit -m "feat(rag): register quiz harness plan/critique prompts, repoint quiz_gen"
```

---

## Task 7: Wire the harness into `generate_quiz_questions` and the API response

The last task: `quiz_generation.generate_quiz_questions` delegates to `quiz_harness.run` instead of
calling `generate_json` directly; `quizzes_api.generate_quiz`'s response carries the new `trace`
field.

**Files:**
- Modify: `app/services/quiz_generation.py:83-108` (`generate_quiz_questions`)
- Modify: `app/api/quizzes_api.py:141-205` (`generate_quiz`)
- Modify: `tests/unit/test_quiz_generation.py:62-85`
- Modify: `tests/integration/test_quizzes_certificates_api.py`

**Interfaces:**
- Consumes: `quiz_harness.run` (Task 5).
- Produces: `generate_quiz_questions(topic, context_items) -> Optional[Dict[str, Any]]` unchanged
  in signature; now returns `{"questions": [...], "trace": {...}}` or `None` (when `run()` produced
  no questions) — same external contract as before, callers that only read `.get("questions")`
  (`lesson_service._persist_quiz`) are unaffected. `POST /courses/{course_id}/quizzes/generate`'s
  JSON response gains a `"trace"` key alongside the existing quiz fields.

- [ ] **Step 1: Write the failing tests**

Replace the two tests in `tests/unit/test_quiz_generation.py` (lines 62-85):
```python
@pytest.mark.asyncio
async def test_generate_quiz_questions_delegates_to_harness():
    with patch("app.services.quiz_generation.quiz_harness.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"questions": _QUESTIONS, "trace": {"final_count": 1}}
        result = await generate_quiz_questions("UTXO model", [{"label": "p1", "text": "...", "chunk_id": "c1"}])

    assert result == {"questions": _QUESTIONS, "trace": {"final_count": 1}}
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_quiz_questions_returns_none_when_harness_produces_nothing():
    with patch("app.services.quiz_generation.quiz_harness.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"questions": [], "trace": {"final_count": 0}}
        result = await generate_quiz_questions("UTXO model", [{"label": "p1", "text": "...", "chunk_id": "c1"}])

    assert result is None
```

In `tests/integration/test_quizzes_certificates_api.py`, change
`test_generate_quiz_persists_to_db`'s patch target from
`"app.services.quiz_generation.generate_json"` to `"app.services.quiz_generation.quiz_harness.run"`,
with `mock_gj.return_value = {"questions": _QUESTIONS, "trace": {"final_count": 1}}`, and add:
```python
        assert body["trace"] == {"final_count": 1}
```
Update Task 1's `test_generate_quiz_uses_evidence_pack_chunk_id` the same way: it now asserts the
`context` kwarg on `quiz_harness.run`'s call (its second positional/keyword argument,
`context_items`) rather than on `generate_json`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_generation.py tests/integration/test_quizzes_certificates_api.py -v`
Expected: FAIL — `generate_quiz_questions` still calls `generate_json` directly; no `trace` key in
the response.

- [ ] **Step 3: Rewrite `generate_quiz_questions` in `app/services/quiz_generation.py`**

```python
from app.services import quiz_harness

_DEFAULT_TARGET_COUNT = quiz_harness.DEFAULT_TARGET_COUNT


async def generate_quiz_questions(
    topic: str,
    context_items: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """Run the plan/generate/critique/repair harness to produce MCQ quiz data.

    Returns None (rather than raising) when the harness produces zero
    questions — quiz generation is treated as best-effort by all current
    callers.
    """
    result = await quiz_harness.run(topic, context_items, target_count=_DEFAULT_TARGET_COUNT)
    if not result["questions"]:
        return None
    return result
```
Delete `QUIZ_PROMPT_VERSION`, `QUIZ_SCHEMA`, and `QUIZ_SYSTEM` (the old lines 23-80) — nothing
calls them after this rewrite (Task 6 already repointed the `"quiz_gen"` registry entry away from
them). Remove the now-unused `StructuredGenerationError`/`generate_json` imports from this file if
nothing else in it still uses them (check `persist_quiz` — it doesn't).

- [ ] **Step 4: Add the `trace` field to the API response in `app/api/quizzes_api.py`**

In `generate_quiz` (around line 196-205), capture the trace before building the response:
```python
    response_body = _to_student_detail(quiz, questions, db).model_dump()
    response_body["trace"] = quiz_data.get("trace")
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=response_body)
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd services/ai && uv run --no-sync pytest tests/unit/test_quiz_generation.py tests/integration/test_quizzes_certificates_api.py tests/unit/test_quiz_harness.py tests/unit/test_prompt_registry.py tests/unit/test_qvac_router.py tests/unit/test_lesson_service.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite and mypy**

Run: `cd services/ai && uv run --no-sync pytest && uv run --no-sync mypy app`
Expected: PASS (no regressions elsewhere — `lesson_service._generate_quiz_data`/`_persist_quiz`
are unaffected since they only read `.get("questions")` off the same dict shape).

- [ ] **Step 7: Commit**

```bash
git add app/services/quiz_generation.py app/api/quizzes_api.py tests/unit/test_quiz_generation.py tests/integration/test_quizzes_certificates_api.py
git commit -m "feat(rag): wire the quiz agent harness into quiz generation and the API response"
```

---

## After merge (not a coded task)

Per issue #134's acceptance criteria: run a manual review of 20 generated questions on real
Bitcoin course material against a live QVAC service, and record pass/fail judgments in the issue
before closing it. This requires a running QVAC worker and is not something these tasks can verify.
