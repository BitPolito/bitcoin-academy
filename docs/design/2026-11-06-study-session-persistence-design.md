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

## Decisions made

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
  already has the full accumulated answer + sources, not by re-parsing SSE frames in
  `study_api.py`. This keeps `study_service` free of a database dependency: the callback is the
  seam, the service itself never touches the DB.
- **Session granularity**: sessions are discrete, explicitly created — not one continuous
  per-course history like today's `localStorage` blob. A new `study_session` is created when the
  user opens the study workspace without resuming an existing one (or explicitly starts a new
  session), matching "session list + resume + delete" in the issue.
- **Citation payload stored per turn**: the anchor fields only (`doc_id`, `doc_name`, `section`,
  `page`, `slide`, `chunk_id`, `chunk_type`) plus the short label/snippet already present in the
  HTTP-facing citation DTO — not the full evidence-chunk text (re-fetchable via `chunk_id` from
  the ingestion store if ever needed). This bounds storage growth given the no-expiry decision.
- **Legacy `localStorage` migration and citation resolvability**: turns migrated from
  `localStorage` (PR4) never had a `chunk_id` available to them (the HTTP DTO they were built
  from drops it) and will carry a null `chunk_id` on their citations — a documented, accepted
  gap. Citations on a restored turn resolving to a chunk is a goal for turns created going
  forward, not a retroactive guarantee for pre-migration history. For the same reason, a stored
  citation missing `doc_id` must degrade gracefully (the anchor is dropped, not the whole turn)
  rather than raise.
- **Delete cascade behavior**: `study_turn` rows are `ON DELETE CASCADE` from their
  `study_session`. `answer_feedback.turn_id` is `ON DELETE SET NULL` — a feedback row survives
  session deletion (it remains useful signal even if the underlying turn/session is gone), it
  just loses the turn linkage. SQLite does not enforce `ON DELETE CASCADE` unless foreign keys
  are turned on for the connection, so the cascade is additionally declared at the ORM level
  (`relationship(..., cascade="all, delete-orphan")`) and that is the path actually exercised in
  this codebase today.
- **Timestamps**: all `study_session`/`study_turn` timestamps are written at the application
  layer as `datetime.now(timezone.utc).isoformat()`, matching the convention used elsewhere in
  the codebase (e.g. `course_repo.py`). No DB-side `func.now()` default/onupdate, to avoid two
  different clocks/formats disagreeing about ordering.

## PR breakdown (what's left to the builder)

1. **PR1 — data model**: `study_session`/`study_turn` SQLAlchemy models, Alembic migration,
   repository, service. Unit tests for repo + service. No API, no dispatch hook yet.
2. **PR2 — sessions API**: REST endpoints (create/list/get/delete), scoped by `current_user.sub`
   and `course_id`.
3. **PR3 — dispatch integration + feedback linkage**: persist a turn from both the buffered and
   streaming dispatch paths, reading citations from the richer `EvidencePack`/`CitationAnchor`.
   Add nullable `turn_id` to `answer_feedback`.
4. **PR4 — frontend**: session list + resume + delete in the study workspace; `localStorage`
   demoted to an optimistic cache; one-time migration of existing `localStorage` content to the
   backend on first load.
5. **PR5 — retention + docs**: document the no-automatic-expiry decision, update
   `docs/specifications.md` per AGENTS.md §7, and add a note in `docs/agent-memory-plan.md`'s
   Phase 4 section pointing at this issue's schema as the (partial) implementation.

Only the PR that completes all of #136's acceptance criteria (PR4) should use `Closes #136` —
the earlier ones use `Refs #136`.
