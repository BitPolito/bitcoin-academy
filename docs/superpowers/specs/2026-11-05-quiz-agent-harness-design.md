# Quiz agent harness — design

Issue: [#134](https://github.com/BitPolito/bitcoin-academy/issues/134) — Agent harness for quiz
generation (plan → generate → critique → repair).

## Intent and why

Quiz generation today (`quiz_generation.generate_quiz_questions`) is a single schema-validated
`generate_json` call: it guarantees well-formed questions, not *good* ones. Observed failure modes
(from the issue): guessable distractors, general-knowledge questions, multiple defensible answers,
coverage clustered on one passage, answers not actually grounded in the cited chunk.

This design replaces that single call, for both callers (course builder per-lesson quizzes and the
study-page ad-hoc quiz action), with a bounded four-stage loop: plan which passages/cognitive
levels to test, generate one question per target, critique each against explicit criteria, repair
(regenerate + re-critique) questions that fail once, then persist through the existing
`persist_quiz` path unchanged.

## Goals

- Each returned question passed the critic, or the run honestly reports why it could not reach the
  target count.
- Bounded, predictable LLM call count per run — no path that can loop unboundedly.
- Deliberate coverage: targets are planned from the evidence pack rather than incidental to however
  the single old prompt happened to sample it.
- A structured trace (targets planned, generated, rejected with reasons, repaired, final count)
  returned to the caller, so quality issues are debuggable without re-reading logs.
- Degrade honestbly when generation is unavailable: fewer questions or a clear error, never
  malformed output (matches existing `generate_quiz_questions` contract of returning `None`/fewer
  items rather than raising on the caller).

## Non-goals / anti-goals

- Not touching `persist_quiz` — the loop produces the same `questions: List[Dict]` shape
  `generate_quiz_questions` returns today; persistence is unchanged.
- Not building a background job / `GenerationRun` row for quizzes. Confirmed with the repo owner:
  stays synchronous, single in-request call, same shape as today's
  `POST /courses/{course_id}/quizzes/generate`.
- Not tier-scaling the call budget. `content_gen`/`judge` task types already route to the **server**
  model via `qvac_router.LADDER_ROUTING` regardless of the caller's local hardware tier — confirmed
  by reading `qvac_router.py`. A tier-scaled cap would be theater: the calls all hit the same shared
  server model regardless of the caller's tier. The cap is instead sized to the question count.
- Not spaced repetition or the "open questions" companion issue — explicitly out of scope per #134.
- Not a frontend debug-page change. Reviewed and confirmed: the existing `debug/page.tsx`'s `quiz`
  dropdown option only exercises evidence-pack retrieval, never calls `POST /quizzes/generate` —
  there is no existing "quiz generation" flow on that page to extend, so adding a trace panel there
  would be new UI, not an extension. Decided: the `trace` field is carried in the API response only
  (see "Trace surface" below); the debug-page control is left to a follow-up issue.

## Context-item shape fix (prerequisite, found during review)

The design assumed both callers' `context_items` already carry a resolvable `chunk_id` the plan
stage can select from. True for the course-builder path — `lesson_service._load_context` already
sets `label` to the chunk id (`context_items.append({"label": cid, "text": rows[cid].text})`) —
but **false for the study-page path**: `quizzes_api.py` builds `context_items` from
`result.citations` (`CitationOut`, only `label`/`doc_id`/`snippet`), which never carries a chunk id.
The real id exists on `result.evidence_pack.chunks[i].chunk_id` (`EvidenceChunk`, already populated
for the `RETRIEVE` action per `study_service.dispatch`) — data already fetched, no new retrieval
call needed.

Fix, as a prerequisite step before the harness lands: both callers add an explicit `chunk_id` key
to each `context_items` dict (confirmed safe — `generate-json.js`'s `buildContextBlock` only reads
`label`/`text`, extra keys are ignored by the worker):

- `lesson_service._load_context`: `context_items.append({"label": cid, "text": rows[cid].text,
  "chunk_id": cid})` (redundant with `label` today, but makes the key explicit and uniform across
  callers rather than relying on the course-builder path's `label`-doubles-as-chunk_id convention).
- `quizzes_api.generate_quiz`: build from `result.evidence_pack.chunks` instead of
  `result.citations`: `context_items = [{"label": c.anchor.doc_name, "text": c.text, "chunk_id":
  c.chunk_id} for c in result.evidence_pack.chunks]`. `result.evidence_pack` can be `None`
  defensively (treat as "no source material", same error path as today's empty-citations check) —
  confirm this doesn't happen for a successful `RETRIEVE` dispatch, but guard it anyway since
  `DispatchResult.evidence_pack` is typed `Optional`.

The harness's `_plan_targets`/`_generate_one` read `item["chunk_id"]` uniformly across both callers
after this fix.

## Constraints (from the issue, confirmed as hard requirements)

- Every returned question carries a resolvable `chunk_id`.
- Hard cap on LLM calls — no unbounded loop.
- Quality criteria the critic must check, verbatim from the issue:
  1. The answer is entailed by the cited source chunk.
  2. Every distractor is plausible but demonstrably wrong from the source.
  3. Exactly one option is defensible.
  4. The question is not answerable without the course material.
  5. The question does not duplicate another in the set.
- Unit tests with a mocked `generate_json` covering: all pass, some rejected then repaired, retry
  limit reached, LLM disabled.
- Manual review of 20 generated questions on real Bitcoin material, results recorded in the issue —
  this is a post-implementation activity for whoever runs it against a live QVAC service, not
  something the code can satisfy; call it out as a follow-up step in the PR, not a coded check.

## Call budget (decided, not tier-scaled)

For a target of `N` questions:

- **Plan**: 1 call — selects `N` `(chunk_id, cognitive_level)` targets from the evidence pack
  already available to the caller (reuses the `context_items` the existing callers already fetch
  via `study_service.dispatch(..., action=StudyAction.RETRIEVE)`; no new retrieval call).
- **Generate**: up to `N` calls — one `generate_json` call per target.
- **Critique**: up to `N` calls — one call per generated question (batching all N into one critique
  call was considered and rejected: a single malformed critique response would then invalidate
  every verdict at once, and the per-lesson judge precedent in `lesson_service._judge_groundedness`
  is also one call per judged unit).
- **Repair**: up to `R` additional (generate + critique) pairs, where `R` = number of questions that
  failed critique on the first pass, each regenerated and recritiqued **once** (confirmed: 1 repair
  round, not more).

Worst case total: `1 + N + N + 2N = 4N + 1` calls. For the existing default of 3-4 questions
(`QUIZ_SCHEMA` in `quiz_generation.py` currently asks the model for 3-4 at once), that's at most 17
calls — each still capped by the existing 300s transport timeout, same ceiling `generate_json`
already imposes per call today. This is the hard cap: the loop tracks calls made and refuses to
start a repair pass once the budget is exhausted, returning what it has with a reported reason.

## The four stages

### 1. Plan

New function, e.g. `_plan_targets(context_items, target_count) -> List[PlanTarget]` where
`PlanTarget = {chunk_id, cognitive_level}` (`cognitive_level` ∈ `recall | application | analysis`).
One `generate_json` call with a new JSON schema (list of `{chunk_id, cognitive_level}`, length
`target_count`) and a new system prompt instructing the model to spread targets across distinct
chunks and levels. `chunk_id` values are constrained to the ones present in `context_items` (reject
and fall back to round-robin assignment across available chunks if the model invents one — this is
a correctness guard, not an LLM call).

### 2. Generate

Reuses the existing generation call shape but one target at a time instead of one call for the
whole batch: `_generate_one(target, context_items) -> Dict | None`. New schema: a single question
object (same shape as one entry in today's `QUIZ_SCHEMA.items`, i.e. `question, options (A-D),
correct_answer, concept_tag, difficulty, chunk_id`), with the prompt pinned to `target.chunk_id`'s
passage and `target.cognitive_level`. On `StructuredGenerationError`, this target is marked failed
at generation (counts against the budget, not a separate "generation failed" dead end — it can
still be retried in the repair pass like a critique failure).

### 3. Critique

New function `_critique(question, source_chunk, other_questions) -> CritiqueVerdict` where
`CritiqueVerdict = {passed: bool, failed_criteria: List[str]}`, one call per question, schema
listing the 5 criteria above as named boolean fields (mirrors `_JUDGE_SCHEMA`'s shape in
`lesson_service.py`) so failures are attributable to a specific criterion in the trace. Duplicate
detection (criterion 5) is checked against the other questions already accepted in this run, passed
in as context — this is the one criterion that needs same-run state, so critique must run after
each generation rather than once over the whole batch in parallel, keeping the loop sequential.
On `(LlmDisabledError, StructuredGenerationError)`, **fail closed** like
`_judge_groundedness` does — treat as `passed=False` with reason `"critic unavailable"`, do not
silently accept.

### 4. Repair

For each question that failed critique, exactly one retry: regenerate via the same `_generate_one`
with the failed criteria appended to the prompt as explicit feedback (e.g. "the previous attempt
was rejected because: ..."), then critique again. Whatever the second verdict is, it is final —
pass → kept, fail → dropped and recorded in the trace with its reasons.

### 5. Persist

Unchanged: the harness's output is the same `questions: List[Dict]` shape
`generate_quiz_questions` already returns; `persist_quiz` is called by the same callers exactly as
today.

## Public API

New module: `services/ai/app/services/quiz_harness.py`. Keeps `quiz_generation.py` as the
persistence + public-entry module (so existing imports in `lesson_service.py` and `quizzes_api.py`
need minimal changes):

```python
async def generate_quiz_questions(
    topic: str, context_items: List[Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    ...
```

stays the public entry point in `quiz_generation.py`, but its body now delegates to the harness:

```python
async def generate_quiz_questions(topic, context_items):
    result = await quiz_harness.run(topic, context_items, target_count=_DEFAULT_TARGET_COUNT)
    if not result.questions:
        return None
    return {"questions": result.questions, "trace": result.trace}
```

`quiz_harness.run(...) -> HarnessResult` where `HarnessResult = {questions: List[Dict], trace:
HarnessTrace}`. `HarnessTrace` is a plain dict (not persisted, not a DB model — see Non-goals):
`{targets_planned: int, generated: int, rejected: [{question_preview, reasons}], repaired: int,
final_count: int, calls_used: int, calls_budget: int}`.

### API response shape change

`POST /courses/{course_id}/quizzes/generate` (`quizzes_api.py`) currently returns the persisted
quiz. Add a `trace` field alongside it (additive, not breaking) sourced from the dict
`generate_quiz_questions` now returns. `lesson_service.py`'s course-builder path can log the trace
(e.g. via `_update_run`'s stage/error fields or a log line) rather than surface it in a UI, since the
course-builder flow has no per-call debug surface today — only the study-page path gets the debug
panel (see below).

## Task-type routing

Add to `qvac_router.LADDER_ROUTING`: `"quiz_plan": ("server", SERVER_MODEL)`, `"quiz_critique":
("server", SERVER_MODEL)`. Generation calls reuse the existing `"content_gen"` task type (no new
entry needed — same model, same routing). This is a deliberate registration (visible in review) even
though `resolve()` would default unknown task types to `server` anyway — explicit entries document
intent, matching how `"judge"` and `"content_gen"` are already registered rather than left to the
fallback.

## Prompt registry

Add `_PLAN_SYSTEM`/`PLAN_PROMPT_VERSION` and `_CRITIQUE_SYSTEM`/`CRITIQUE_PROMPT_VERSION` constants
in `quiz_harness.py`, registered in `prompts/registry.py::_build_registry()` following the existing
`"judge"` entry pattern (import `quiz_harness`, add `"quiz_plan"` and `"quiz_critique"` entries).
Generation keeps using `quiz_generation`'s existing `QUIZ_PROMPT_VERSION`/`QUIZ_SYSTEM` (already
registered as `"quiz_gen"`), adjusted to operate on one target instead of a batch.

## Debug surface

Decided (revised after review — see Non-goals): no frontend change in this PR. The `trace` field
rides in the existing `POST /quizzes/generate` JSON response body, inspectable via the API directly
(curl, API client, or browser devtools network tab) without any new backend route. A follow-up
issue should add an actual trigger-and-display control to `debug/page.tsx`, since today's `quiz`
dropdown option there only runs evidence-pack retrieval, not real generation — building that control
is new UI work, not an extension of something that already calls the generate endpoint.

## Testing

Follow the existing mocking convention (patch `generate_json` where imported into the calling
module, i.e. `app.services.quiz_harness.generate_json`, with `AsyncMock`):

- All pass: each stage's mock returns a passing verdict; assert `calls_used` matches the
  no-repair-needed budget (`1 + 2N`) and all `N` questions returned.
- Some rejected then repaired: first critique fails for a subset, second (repair) critique passes;
  assert those questions appear in `trace.repaired` and the final set, with `calls_used` reflecting
  the extra repair calls.
- Retry limit reached: repair critique also fails; assert the question is dropped, appears in
  `trace.rejected` with its final reasons, and the loop does not attempt a third pass.
- LLM disabled: `generate_json` raises `LlmDisabledError` at the plan stage; assert the harness
  returns no questions with a clear reason rather than raising, matching
  `generate_quiz_questions`'s existing `None`-on-failure contract.
- Persistence path (`persist_quiz`) is untested here since it is unchanged — existing
  `test_quiz_generation.py` coverage stands.

## What's left to the builder

- Exact wording of the plan/critique system prompts (content, not structure — structure is fixed
  above).
- Exact JSON schema field names/ordering for `PlanTarget`, the single-question generation schema,
  and `CritiqueVerdict` (shape is specified; naming is the builder's call, following existing
  snake_case conventions in `quiz_generation.QUIZ_SCHEMA`/`lesson_service._JUDGE_SCHEMA`).
- Whether `_DEFAULT_TARGET_COUNT` stays at today's 3-4 (as a range) or becomes a fixed single number
  now that generation is per-target — builder's call, defaulting to keeping the existing range
  (e.g. target_count = 4, allow the plan stage to return 3 if the evidence pack has too few distinct
  chunks to avoid forcing duplicate-chunk targets).
- Whether `quiz_harness.py` or `quiz_generation.py` owns the `HarnessTrace`/`PlanTarget` type
  definitions — builder's call; suggested: define them in `quiz_harness.py` since it owns the loop.
