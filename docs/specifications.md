# BitPolito Academy — Functional Requirements

> **Status:** current as of the project realignment (supersedes the earlier PDF specification).
> Each requirement carries a verified implementation status. See [`overview.md`](overview.md) for
> vision and architecture.

## Status legend

| Badge | Meaning |
|---|---|
| ✅ **Implemented** | Present in the codebase and working as specified |
| 🟡 **Partial** | Implemented in part, or implemented differently from the original specification |
| 🔴 **Not implemented** | Scaffolding only, or absent |

Requirements 1–20 are the original specification. Requirements 21–27 document capabilities that
exist in the product but were never captured in the historical specification.

---

## Part I — Original requirements

### 1. Course workspace creation and document ingestion — ✅ Implemented

The system must allow users to create a dedicated course workspace and upload course materials,
including at least PDF and PPTX files. Each uploaded file must be associated with a specific course
and tracked as an individual document.

**Implementation.** Courses are created via the courses API and each becomes an isolated workspace
keyed by `course_id`. Upload accepts PDF, PPTX and DOCX (DOCX exceeds the original requirement).
Every file is persisted as a `CourseDocument` row with its own lifecycle.

---

### 2. Multi-file upload and per-file tracking — ✅ Implemented

The system must support multi-file upload with per-file lifecycle tracking, exposing upload
progress, backend processing status, success/failure state, a retry option, and clear error
messages.

**Implementation.** The upload component tracks each file independently; the documents API exposes
processing status per document, supports retry and deletion, and surfaces actionable errors. A
processing panel and progress indicator render the state in the course workspace.

---

### 3. Document parsing and normalization — ✅ Implemented

The system must parse uploaded materials into a structured internal representation preserving
extracted text, page/slide segmentation, document hierarchy, source anchors, and enough structure
for downstream chunking, retrieval, and source-grounded UI.

**Implementation.** `pymupdf4llm` (PDF, page-chunked), `python-pptx` (per slide) and DOCX parsers
feed a normalisation stage. Parser-specific artefacts (LaTeX running headers, typesetting noise,
OCR noise) are cleaned. Docling is available as an opt-in parser — see requirement 25.

---

### 4. Structured document storage — ✅ Implemented

Parsed and normalized content must be stored so it can be inspected and reused by downstream
components, supporting both backend processing and UI-level source inspection.

**Implementation.** A normalized document schema is persisted and exposed through debug endpoints
(`/documents/{doc_id}/parsed`, `/documents/{doc_id}/chunks`) and a document preview page.

---

### 5. Hierarchical chunking — ✅ Implemented

Normalized content must be split into hierarchical chunks enriched with metadata: course, document,
section, page/slide, chunk identifier, chunk type.

**Implementation.** Parent-child hierarchical chunking with configurable overlap. Child chunks are
used for retrieval precision; parents provide context at generation time via parent expansion. All
required metadata fields are carried, plus dedicated chunk types (including formula/code blocks and
`past_exam`).

---

### 6. Retrieval-ready indexing — ✅ Implemented

Chunks must be indexed to support semantic retrieval and metadata-aware filtering, compatible with
the RAG pipeline and local execution constraints.

**Implementation.** Chunks are written as JSONL to the QVAC ingest directory and indexed into a
per-course QVAC workspace with a sidecar metadata map. ChromaDB remains a passive fallback,
disabled by default.

---

### 7. Retrieval over course materials — ✅ Implemented

Given a user request, the system must return the most relevant candidate chunks and preserve their
source metadata.

**Implementation.** Dense retrieval over the course workspace returns chunks with full citation
metadata (document, page, slide, section, chunk and parent ids).

---

### 8. Retrieval refinement and evidence-pack assembly — 🟡 Partial

The system must refine retrieved candidates through ranking/reranking, redundancy removal,
evidence-pack assembly, and preservation of source anchors.

**Implementation.** All refinement primitives exist and are implemented to a high standard:
deduplication, action-specific boosting, cross-encoder reranking, MMR diversification, token-aware
truncation, parent expansion, and contextual compression.

**Gap.** These are not applied uniformly. The full hybrid pipeline (dense + BM25 sparse retrieval,
normalised fusion, reranking, MMR) currently runs in the conversational path, while the study
actions use dense-only retrieval with a small candidate pool — meaning the reranker reorders few
candidates and no sparse retrieval contributes. Consolidating the two paths is planned work.

---

### 9. Evidence-pack contract — ✅ Implemented

A consistent intermediate structure must represent the final retrieval context, including the
original query, selected passages, final ordering, deduplicated passages, section/document
metadata, and citations or source anchors.

**Implementation.** The evidence pack is an explicit, well-modelled contract carrying query,
action, ranked chunks, candidate count, ordering, deduplicated passages, token estimate, truncation
flag, and source list. Each chunk carries a citation anchor. It also renders the numbered
`[ref_N]` context block consumed by generation.

---

### 10. Source-grounded study outputs — ✅ Implemented

Study outputs must be generated only from retrieved and filtered evidence, supporting at least
concept explanations, section summaries, open questions, quiz questions, and oral-exam prompts.

**Implementation.** All five output types are supported, plus derivations and comparisons. Prompts
instruct the model to answer using only the provided context and to state explicitly when the
answer is absent from it.

---

### 11. Source linking and citation visibility — ✅ Implemented

Explicit links between generated outputs and original source material must be preserved, and users
must be able to inspect and navigate back to the relevant source location.

**Implementation.** The model emits inline `[ref_N]` markers which are parsed back into citation
objects carrying document, page, slide and section. The UI renders citation cards and a source pane
that navigates to the originating passage.

---

### 12. Study action routing — ✅ Implemented

The system must support explicit study actions rather than generic chat behaviour, and must define
for each action whether retrieval, generation, and source grounding are required.

**Implementation.** A typed action registry declares exactly these properties per action, together
with description, output type and an example query, and is exposed to the frontend. The six
required actions are implemented, plus `derive` and `compare`.

---

### 13. Minimal request dispatcher — ✅ Implemented

A minimal orchestration layer must route study requests, supporting retrieval-only flows,
retrieval + generation flows, fallback handling on failure, and structured request/response
handling.

**Implementation.** The dispatcher routes by registry metadata, supports a retrieval-only mode for
every action, falls back to raw retrieval when generation is unavailable, validates input, and
emits a structured trace per request.

---

### 14. Course workspace and document management — ✅ Implemented

Users must be able to view uploaded documents, inspect processing and indexing status, navigate
course materials, and inspect parsed or processed outputs.

**Implementation.** The course workspace lists documents with status, exposes a processing detail
panel, a lesson navigator, and a parsed-document preview page.

---

### 15. Past exam ingestion and exam-oriented retrieval support — 🟡 Partial

Past exam material must be ingestible and usable to enrich retrieval, identify recurring or
high-impact topics, and support exam-oriented study flows.

**Implementation.** A `past_exam` chunk type exists and receives a relevance boost for the `quiz`
and `oral` actions, so past-exam content is favoured in exam-oriented flows.

**Gap.** There is no dedicated ingestion flow marking a document as a past exam, and no analysis
that identifies recurring or high-impact topics across exams. Currently the chunk type is not
populated by a user-facing path.

---

### 16. Evaluation and debugging support — ✅ Implemented

The system must expose enough internal visibility to evaluate retrieval quality and debug document
processing: processing status, parsed output samples, chunk samples, retrieval candidates, reranked
results, evidence-pack examples, and parser quality notes.

**Implementation.** A dedicated debug API (parsed output, chunks, retrieval candidates, evidence
packs, pipeline health) is exposed in development, backed by a debug page in the UI. A structured
dispatch trace is logged per request. An end-to-end RAG suite scores curated queries across
categories for baseline comparison.

---

### 17. Local-first execution — ✅ Implemented

The system must be runnable locally without requiring a cloud-only architecture.

**Implementation.** Embeddings and generation run locally through the QVAC service; no external API
key is required. SQLite is the development database. Generation can be disabled entirely for
memory-constrained machines, leaving retrieval fully functional.

---

### 18. Course isolation — ✅ Implemented

Each course must be kept in a separate workspace so ingestion, retrieval, evidence packs, and
generated outputs remain course-specific.

**Implementation.** `course_id` is the workspace key throughout ingestion, retrieval, caching and
dispatch, with per-course indexes and metadata files.

---

### 19. Compatibility with QVAC-backed RAG workflows — ✅ Implemented

The system must be compatible with the QVAC-based RAG layer, with product-level logic defined above
the lower-level RAG utilities.

**Implementation.** The QVAC service exposes narrow retrieval and generation primitives; action
routing, evidence-pack structure and grounding behaviour live in the Python layer above it.

---

### 20. Extensibility for future study features — 🟡 Partial

The system must be structured so future features can be added without redesigning the core
ingestion, retrieval, and evidence-pack pipeline.

**Implementation.** The action registry, evidence-pack contract and layered service design make new
study actions and features straightforward to add.

**Gap.** The duplicated retrieval paths (requirement 8) mean retrieval improvements must currently
be applied twice, which works against extensibility until consolidated.

---

## Part II — Requirements not present in the historical specification

These capabilities exist in the product and are officially in scope, but were never specified.

### 21. Authentication, authorization and account security — ✅ Implemented

The system must authenticate users and protect its endpoints.

**Implementation.** JWT-based authentication with refresh, a token blacklist for revocation,
account lockout after repeated failures, `admin`/`student` roles, rate limiting, security headers
and audit middleware. Development accounts are seeded automatically, and seeding refuses to run
when `ENVIRONMENT=production`.

Endpoint protection is asserted structurally rather than by convention:
`tests/integration/test_authorization_matrix.py` derives the endpoint list from the live OpenAPI
schema, so an endpoint added without authentication fails the build. Endpoints that are deliberately
public are listed explicitly in `PUBLIC_ENDPOINTS`, which makes publishing one a visible decision.

Two defects in this area were found and fixed by that suite: sixteen endpoints across the courses
and documents APIs declared no authentication at all, and logout blacklisted a refresh token whose
`jti` the refresh endpoint never checked — so a revoked token kept minting access tokens until it
expired on its own.

**Not yet implemented.** Refresh token rotation with reuse detection.

---

### 22. Course structure and study path — ✅ Implemented

The system must model a course as a navigable structure rather than a flat document bag.

**Implementation.** A `Course → Chapter → Lesson` hierarchy with resources, backed by repositories
and exposed through the courses API and lesson navigation UI.

---

### 23. Progress tracking and badges — ✅ Implemented

The system must track study progress and reward milestones.

**Implementation.** Progress is tracked at lesson, chapter and course level, with a progress API and
a badge system (definitions plus per-user awards) rendered in the UI.

---

### 24. Assessment: quizzes and chapter tests — 🔴 Not implemented

The system must let students take quizzes and chapter tests, and must record attempts and scores.

**Implementation.** The data model is complete and migrated (quizzes, questions, options, chapter
tests, attempts, per-answer records), and the API surface is defined with typed request/response
schemas.

**Gap.** The endpoints are stubs: listing returns an empty collection and the detail and submission
endpoints return not-found. The quiz service contains no logic. Note that this entity-based quiz is
distinct from the `quiz` **study action**, which is fully implemented and generates questions from
retrieved evidence.

---

### 25. Completion certificates — 🔴 Not implemented

The system must issue completion certificates and allow public verification by code.

**Implementation.** The certificate entity is modelled and migrated, and both endpoints (list own
certificates, verify by code) are defined.

**Gap.** The endpoints are stubs returning an empty list and an always-invalid verification. The
certificate service contains no logic.

---

### 26. Conversational Q&A with history — ✅ Implemented

Beyond explicit study actions, the system must support free-form follow-up questions with
conversational context.

**Implementation.** A chat endpoint accepts conversation history and answers through the full
hybrid retrieval pipeline, with token streaming to the client. See the consolidation note in
requirement 8.

---

### 27. Performance, resilience and feedback — ✅ Implemented

The system must avoid recomputing identical work, degrade gracefully, and collect quality signals.

**Implementation.** A semantic cache keyed by query, action and course short-circuits near-identical
requests. Background ingestion runs on a queue. Generation failures fall back to raw retrieval.
Students can submit feedback on answer quality, persisted for later analysis.

---

## Summary

| Status | Count | Requirements |
|---|---|---|
| ✅ Implemented | 22 | 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21, 22, 23, 26, 27 |
| 🟡 Partial | 3 | 8, 15, 20 |
| 🔴 Not implemented | 2 | 24, 25 |

The study core specified in Part I is substantially complete. The open work concentrates in three
areas: unifying the two retrieval paths (requirement 8, which also unblocks 20), completing the
assessment and certificate layer (requirements 24 and 25), and building a real past-exam flow
(requirement 15).

---

## Configuration notes

Selected behaviours are configurable and their defaults matter when reading this document:

| Setting | Default | Effect |
|---|---|---|
| Generation enabled | on | Disable for retrieval-only mode on low-memory machines |
| Hybrid/HyDE query expansion | on | Expands the retrieval query |
| Query rewriting | off | Rewrites the raw question before dense retrieval |
| Context compression | on | Trims passages to relevant sentences before generation |
| Contextual chunking | off | Prepends generated context prefixes at ingest time |
| Semantic cache | on | Requires Redis |
| Docling parser | off | Opt-in higher-quality PDF parsing with fallback |
| ChromaDB indexing | skipped | QVAC-only indexing by default |

The full variable reference lives in the README and the configuration document.
