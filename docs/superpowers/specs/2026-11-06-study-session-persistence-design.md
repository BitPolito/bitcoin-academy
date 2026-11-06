# Design: server-side persistence of study sessions

Issue: [#136](https://github.com/BitPolito/bitcoin-academy/issues/136)

## Intent and why

Study session state today lives only in the browser, in a single `localStorage` blob per
course (`apps/web/src/components/study/OutputPane.tsx`, `STORAGE_PREFIX = 'study:'`). Clearing
site data, switching browsers, or using a second device loses the entire study history.
`answer_feedback` rows reference a `session_id` that is a fresh `crypto.randomUUID()` generated
on every component mount and never persisted server-side, so feedback cannot be traced back to
what was actually asked. Streaming responses are not persisted at all today (filtered out of the
`localStorage` path).

This work gives the backend a durable record of study interactions (`study_session` +
`study_turn`), scoped to user and course, and makes the frontend treat the server as the source
of truth with `localStorage` as an optimistic cache at most.

It is explicitly rung 0 ("DB / precomputed assets") of the inference ladder described in
`docs/agent-memory-plan.md` (see issue #131) — work served from the database before any model is
consulted.

## Goals

- A study session (and its turns) survives logout, browser change, and device change.
- Citations on a restored turn still resolve to document / page-or-slide / chunk.
- No cross-user or cross-course leakage of sessions or turns.
- Streaming and buffered dispatch paths persist turns identically.
- `answer_feedback` references a real, persisted turn instead of free-text duplicated from the
  client.
- Existing `localStorage` study history is migrated into the backend once, then the frontend
  stops writing it as the source of truth.

## Non-goals

- A generic, reusable event-log table (`session_event` with arbitrary `event_type`/
  `payload_json`) as sketched in `docs/agent-memory-plan.md` Phase 4. We are building a schema
  specific to study turns (action, query, answer, citations, evidence pack reference, timing,
  model/tier). `docs/agent-memory-plan.md` gets updated to say this issue implements part of
  Phase 4 with a more specific schema, rather than silently diverging from it.
- Course enrollment / ACL. No such concept exists anywhere in the codebase today (confirmed:
  `courses_api.py` only gates by role, never by "is this user enrolled"). "Course isolation"
  here means filtering session/turn queries by `course_id`, not an enrollment check.
- A session/turn concept for the plain `chat` endpoints (`chat_api.py`/`chat_service.py`). Issue
  #136 is scoped to the `study` dispatch path (`study_api.py`/`study_service.py`). Chat turn
  persistence is out of scope unless a future issue asks for it.
- Retention/expiry automation. See "Retention policy" below.
- Spaced repetition, "resume where you left off" UX beyond a plain session list, and any
  student-memory distillation (later phases of `agent-memory-plan.md`).

## Anti-goals (would make this a failure even if technically working)

- A schema change that forces `study_service.py` to take on a database dependency. It currently
  has zero SQLAlchemy imports and is a pure function of `(question, course_id, action)`; it
  should stay that way. Persistence is orchestrated from the API layer and/or a thin service
  call around the existing dispatch functions, not threaded into `study_service`'s internals as
  a parameter plumbed through every call.
- Persisting the lossy `SourceChunk`/`CitationOut` DTOs that are actually returned over HTTP
  (they drop `chunk_id`). Citations must be persisted from the richer `EvidencePack`/
  `EvidenceChunk.anchor`, which already flows through `DispatchResult.evidence_pack` server-side
  but is not exposed in the HTTP response.
- Breaking the existing `answer_feedback` contract for in-flight clients without a compatible
  migration path.

## Constraints (from AGENTS.md and existing architecture)

- Layering: controllers do HTTP + error mapping only; repositories are plain functions over a
  `Session` (no class-based unit-of-work exists despite the stub in `app/core/uow.py` — follow
  the function-based `app/repositories/*.py` pattern, e.g. `progress_repo.py`).
- Every PR targets `master`, is reviewed, and must keep the quality gate green. Target ~400
  lines of meaningful diff per PR — this issue is split into five PRs (below) for that reason.
- Database changes require an Alembic migration (template: `0002_answer_feedback.py` or
  `0008_outline_edit_provenance.py` — guarded `has_table`/`get_columns` checks). Verify the next
  free revision number via `alembic history` before naming the file; do not assume the number
  implied by `agent-memory-plan.md` (`0007`) is still free.
- The evidence pack shape is a pinned contract (`tests/unit/test_contracts.py`). This work reads
  from it but must not change its shape.
- New endpoints are automatically checked by `tests/integration/test_authorization_matrix.py` —
  just requires the standard `Depends(get_current_user)`.
- RAG evaluation suite only applies to retrieval/ranking changes; this work does not change
  retrieval, so it is not required to re-run it.

## Decisions made (in this conversation)

- **Schema shape**: a study-specific schema (`study_session`, `study_turn`), not the generic
  `session_event` sketched in `agent-memory-plan.md`. `agent-memory-plan.md`'s Phase 4 checklist
  gets a note in PR5 pointing at this issue as a (partial, more specific) implementation,
  instead of leaving two parallel, unreconciled designs in the repo.
- **Retention**: no automatic expiry for now. Sessions persist until a user explicitly deletes
  one. Documented as a deliberate choice in PR5's `docs/specifications.md` update; revisit if a
  real storage/privacy need shows up later.
- **`answer_feedback` linkage**: add a nullable `turn_id` FK in PR3 (migration), alongside the
  existing `session_id`/`question`/`answer` text columns (kept for backward compatibility with
  any in-flight clients during rollout). The feedback API starts preferring `turn_id` once the
  frontend sends it; a follow-up can drop the free-text columns once no client paths write
  without a `turn_id`, but that cleanup is not part of this issue.
- **Streaming persistence hook point**: `study_service.dispatch`/`stream_dispatch` stay
  DB-agnostic (no SQLAlchemy import, no `Session` parameter). The API layer passes an optional
  persistence callback into them; it is invoked at the same points where `_cache_and_sentinel`
  already has the full accumulated answer + sources (four call sites in `stream_dispatch`, one
  path in `dispatch`), not by re-parsing SSE frames in `study_api.py`. This keeps the anti-goal
  ("`study_service` must not take on a database dependency") and decision #4 consistent: the
  callback is the seam, the service itself never touches the DB.
- **Session granularity**: sessions are discrete, explicitly created — not one continuous
  per-course history like today's `localStorage` blob. A new `study_session` is created when the
  user opens the study workspace without resuming an existing one (or explicitly starts a new
  session), matching "session list + resume + delete" in the issue. PR2's create-endpoint and
  PR4's UX are built around picking an existing session to resume or starting a new one, not a
  single implicit session per course.
- **Citation payload stored per turn**: the anchor fields only (`doc_id`, `doc_name`, `section`,
  `page`, `slide`, `chunk_id`, `chunk_type`) plus the short label/snippet already present in the
  HTTP-facing citation DTO — not the full evidence-chunk text (re-fetchable via `chunk_id` from
  the ingestion store if ever needed). This bounds storage growth given the no-expiry decision.
- **Legacy `localStorage` migration and citation resolvability**: turns migrated from
  `localStorage` (PR4) never had a `chunk_id` available to them (the HTTP DTO they were built
  from drops it) and will carry a null `chunk_id` on their citations — a documented, accepted
  gap. "Citations on a restored turn resolve to a chunk" is a goal for turns created going
  forward, not a retroactive guarantee for pre-migration history.
- **Delete cascade behavior**: `study_turn` rows are `ON DELETE CASCADE` from their
  `study_session`. `answer_feedback.turn_id` is `ON DELETE SET NULL` — a feedback row survives
  session deletion (it remains useful signal even if the underlying turn/session is gone), it
  just loses the turn linkage.

## PR breakdown (what's left to the builder)

1. **PR1 — data model**: `study_session`/`study_turn` SQLAlchemy models in `app/db/models.py`,
   Alembic migration, `app/repositories/study_session_repo.py`, `app/services/
   study_session_service.py` (create/list/get/delete session, append turn — function-based,
   following `progress_repo.py`/`progress_service.py`). Unit tests for repo + service. No API,
   no dispatch hook yet.
2. **PR2 — sessions API**: REST endpoints (create/list/get/delete), scoped by
   `current_user.sub` and `course_id` (filter, not enrollment-check — see non-goals). Integration
   tests for success/failure/isolation paths. Relies on `test_authorization_matrix.py` for the
   auth-presence check.
3. **PR3 — dispatch integration + feedback linkage**: persist a turn from both the buffered
   path (`study_api.py`, right after `study_service.dispatch(...)`) and the streaming path
   (`study_service.stream_dispatch`, at the `_cache_and_sentinel` call sites), reading citations
   from the richer `EvidencePack`/`CitationAnchor` (has `chunk_id`), not the HTTP-facing DTOs.
   Add nullable `turn_id` to `answer_feedback` (migration + schema + API change). Tests:
   persistence parity between streaming and buffered, cross-user/cross-course isolation
   (explicit negative tests), citation resolvability after restore.
4. **PR4 — frontend**: session list + resume + delete in the study workspace; `localStorage`
   demoted to an optimistic cache; one-time migration of existing `localStorage` content to the
   backend on first load, after which the frontend stops treating it as the source of truth.
   Replace `sessionIdRef`'s per-mount UUID with the real persisted session id. Unit/integration
   tests per the existing frontend testing conventions.
5. **PR5 — retention + docs**: document the no-automatic-expiry decision, update
   `docs/specifications.md` per AGENTS.md §7, and add a note in `docs/agent-memory-plan.md`'s
   Phase 4 section pointing at this issue's schema as the (partial) implementation.

Each PR is opened against `master` from a branch created from an up-to-date `master`
(`feat/study-session-<slice>`), per AGENTS.md §3. PR1–PR3 are backend-only and can each close out
a sub-scope of #136; PR4 is frontend; PR5 is docs/policy. Only the PR that completes all of
#136's acceptance criteria (PR4, since it finishes the frontend requirement) should use
`Closes #136` — the earlier ones use `Refs #136`.
