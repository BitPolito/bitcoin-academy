# Cross-course topic taxonomy: the isolation boundary

Status: decided for the first implementation slice (#139). Revisit only with an
explicit new design discussion, not as a side effect of a feature PR.

## The question

Course isolation (`docs/specifications.md`, requirement 18) means retrieval,
evidence packs and generated output stay bound to the course they came from.
Issue #139 asks for a topic layer that *does* cross course boundaries — the
same concept ("UTXO", "Merkle tree") taught in two different courses should be
recognized as one thing. Those two requirements are in tension, and the issue
itself names this as the crux of the design to settle before writing code.

## Decision

**The topic taxonomy is a navigation and explanation layer. It never widens
what retrieval can read, and it never changes what feeds an answer.**

Concretely:

1. **Retrieval is unaffected.** Nothing in `app/rag/retriever.py`,
   `hybrid_search.py`, `parent_expansion.py` or `evidence_pack_service.py` may
   query, filter, or boost by topic. The workspace key for retrieval stays the
   course id, exactly as today. A topic row existing, or a topic having
   occurrences in multiple courses, must not change which chunks a query can
   return.
2. **The evidence pack contract is unaffected.** The pack passed to generation
   for course A may only ever contain chunks whose `doc_id` resolves to a
   document belonging to course A. Topic data is not an input to
   `evidence_pack_service.build_from_chunks` or to `study_service.dispatch`.
   This is asserted by test, not just documented — see
   `tests/integration/test_course_isolation.py::test_evidence_pack_never_mixes_chunks_across_courses`.
3. **Cross-course surfacing is opt-in and explicit, always attributed.** When a
   later slice builds the "where else is this covered" UI, it is a separate,
   clearly-labelled user action (e.g. "Show this topic in other courses") that
   the student actively takes. It is never shown inline in an answer, never
   triggered by a RAG query, and every cross-course result it surfaces must be
   attributed to its originating course so the student knows the material
   did not come from the course they are currently studying.
4. **Topics are a read-side index, not a write-side dependency.** Course
   content generation (outline pipeline, lesson content generation, quiz
   generation) does not read from or depend on the topic tables. If the topic
   layer were deleted entirely, course generation and study sessions would be
   unaffected. This keeps the taxonomy an additive layer that can be iterated
   on, or re-derived from scratch, without touching the content pipeline.

## What this rules out, explicitly

- No embedding- or LLM-based cross-course query expansion ("the student asked
  about X, X is also covered in course B, so pull B's chunks in too"). That is
  exactly the widening this decision forbids.
- No merging of evidence packs across courses under any circumstance,
  including same-topic matches.
- No implicit surfacing: a topic page listing cross-course occurrences does
  not get auto-opened by the study workspace. The student has to ask for it.

## Why this shape

The alternative — letting a shared topic identity leak into retrieval scope —
would reintroduce the problem requirement 18 exists to prevent, and it would
do so quietly: nothing in a single-course deployment would reveal the leak,
exactly like the course-isolation bugs the existing test suite is designed to
catch before multi-course deployments expose them to real users.

## Alias resolution: manual curation only (this slice)

The issue's own stated risk is explicit: "Getting alias resolution wrong
conflates distinct concepts, which is worse than not linking them at all.
Prefer precision over recall, and prefer manual curation for the first pass."

This slice follows that instruction literally:

- Aliases are added to a canonical topic only through an explicit curation
  action (`topic_service.add_alias`), not inferred.
- Occurrence matching against lesson text uses exact, case-insensitive,
  word-boundary matching against the canonical name and its curated aliases —
  no fuzzy matching, no embedding similarity, no LLM adjudication.
- Prerequisite relations seeded from the outline's pedagogical ordering are
  marked with `source="outline_seed"` so they are visibly distinct from
  human-curated relations (`source="manual"`) and can be reviewed or removed
  without guessing at their origin.

Automatic, similarity-based alias merging (embeddings or an LLM adjudicator)
is deliberately out of scope for this slice. It is the riskier of the options
the issue lists, and the issue asks for it to be justified, not defaulted
into. If a later slice wants it, it needs its own design note weighing
precision loss against the curation burden it would remove — it cannot be
added as an incidental improvement to this foundation.

## Scope of this decision

This document governs the data-layer PR that introduces `topic`,
`topic_alias`, `topic_occurrence` and `topic_relation`. It does not cover the
topic view UI, prerequisite hints in the study workspace, or the cross-course
exploration UI — those are later slices of #139 and must be designed against
the constraints above, not against convenience.
