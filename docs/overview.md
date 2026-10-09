# BitPolito Academy — Project Overview

> **Status:** current as of the project realignment (supersedes the earlier PDF overview).
> For the requirement-by-requirement implementation status, see [`specifications.md`](specifications.md).

BitPolito Academy is an open-source, local-first study companion designed for students who,
especially in technical subjects, need more than simple summaries. The project addresses some of
the most common weaknesses of AI-based study tools: the flattening of conceptual structure, the
loss of argumentative logic, and the tendency to create passive familiarity instead of
transferable understanding. In practice, many tools help students "read faster," but do not truly
prepare them to explain a concept, justify a result, discuss exceptions, compare alternatives, or
connect distant parts of a course.

BitPolito Academy is built to solve exactly this problem. It is not intended to be a generic
chat-with-documents system, but a structured study environment that reconstructs the logic of a
course from slides, notes, handouts, and past exams. In this setting, AI does not replace active
study; it supports it. Its role is to retrieve the right sources, organize the relevant context,
generate grounded explanations and summaries, and, above all, help students stress-test their
understanding through open questions, quizzes, and oral-exam prompts.

The first use case is the Bitcoin protocol and adjacent technical subjects, a domain that is
particularly suitable because it combines formal mechanisms, layered systems, trade-offs, edge
cases, and strong dependence on source texts and lecture logic.

---

## 1. Product scope

The product is organised in two layers, both officially in scope.

### 1.1 Study layer (core)

The study layer is the heart of the product. Course materials are uploaded, parsed, and converted
into a structured internal representation. The content is then split into hierarchical chunks
enriched with metadata such as course, document, section, and page or slide. On top of this
structure, the system performs retrieval and reranking in order to select the passages most
relevant to a study request. The results are assembled into an ordered, deduplicated **evidence
pack** linked back to the original sources, which becomes the actual context used by the
generation layer. In this way, the model does not operate opaquely over the entire corpus, but
only over filtered, inspectable evidence.

From the user's perspective, the core interactions are not generic conversations but explicit
**study actions**. The system currently supports eight:

| Action | Retrieval | Generation | Output | Source-grounded |
|---|---|---|---|---|
| `explain` | yes | yes | prose | yes |
| `summarize` | yes | yes | list | no |
| `retrieve` | yes | no | chunks | yes |
| `open_questions` | yes | yes | list | no |
| `quiz` | yes | yes | Q&A pairs | yes |
| `oral` | yes | yes | Q&A pairs | yes |
| `derive` | yes | yes | prose | yes |
| `compare` | yes | yes | prose | yes |

`derive` and `compare` were added after the original specification: they cover step-by-step formal
derivations and side-by-side reconciliation of concepts across sources, both of which are frequent
needs in technical exams. `compare` and `derive` additionally use a two-hop retrieval strategy that
splits multi-entity questions and merges the resulting evidence.

### 1.2 Learning-management layer

Alongside the study layer, the platform provides the structure of a course-based learning
environment: user accounts and roles, a `Course → Chapter → Lesson` hierarchy, progress tracking at
lesson, chapter, and course level, badges, assessment (quizzes and chapter tests), and completion
certificates. A conversational endpoint with history complements the explicit study actions for
free-form follow-up questions.

This layer is officially part of the product. Some of its components are complete (authentication,
progress, badges) while others are currently scaffolding only (quiz backend, certificates) — see
[`specifications.md`](specifications.md) for the exact status of each.

---

## 2. Technical principles

The project follows a set of clear technical principles:

- **Local-first.** The whole system runs on the user's machine. Embeddings and generation are
  served by a local QVAC-backed service; no external LLM API key is required.
- **Open-source.** MIT licensed.
- **Retrieval-first.** Generation is always downstream of retrieval; the model consumes an
  inspectable evidence pack, never the raw corpus.
- **Deterministic where possible.** Parsing, chunking, ranking, dedup, and dispatch are explicit,
  traceable code paths rather than emergent model behaviour.
- **Course isolation.** Each course lives in its own workspace, so ingestion, retrieval, evidence
  packs, and generated outputs remain tied to the material of that subject.
- **Source-grounded output.** Generated answers carry inline citation markers resolved back to the
  originating document, page, or slide.
- **Graceful degradation.** With generation disabled, every study action still returns source
  passages, so the system remains usable on memory-constrained machines.

The overall quality of the product depends primarily on parsing, chunking, metadata, retrieval, and
grounding, rather than on the generative model alone.

---

## 3. System architecture

The system is a monorepo composed of three deployable services plus supporting infrastructure.

```
apps/web            Next.js (App Router) + NextAuth  — user interface
services/ai         FastAPI + SQLAlchemy + ARQ       — API, ingestion, RAG orchestration
workers/qvac-service  Node + @qvac/sdk               — local embeddings and LLM
```

| Component | Technology | Responsibility |
|---|---|---|
| **Web** | Next.js, NextAuth, Tailwind | Course list, upload, study workspace, source pane, document preview, debug console |
| **API** | FastAPI, SQLAlchemy, Pydantic | Authentication, courses, documents, study dispatch, chat, progress, debug endpoints |
| **Worker** | ARQ | Background ingestion pipeline |
| **RAG engine** | Node, `@qvac/sdk` | GTE-Large FP16 embeddings, Qwen3-4B generation, dense search over course workspaces |
| **Database** | SQLite (dev) / PostgreSQL (prod), Alembic | Users, courses, documents, chunks, progress, assessment |
| **Cache/queue** | Redis | Semantic cache, background jobs, token blacklist, account lockout |
| **Proxy** | Caddy | TLS termination and routing in production |

Internally the API follows a layered design: controllers (`app/api`) → services (`app/services`) →
repositories (`app/repositories`) over a unit-of-work, with Pydantic schemas as explicit contracts
between layers.

### 3.1 Ingestion pipeline

1. **Upload** — multi-file upload with per-file lifecycle tracking.
2. **Parsing** — `pymupdf4llm` for PDF, `python-pptx` for slides, and DOCX support; Docling is
   available as an opt-in higher-quality PDF parser with automatic fallback.
3. **Normalisation** — parsed output is converted into a structured document schema preserving
   text, page/slide segmentation, hierarchy, and source anchors.
4. **Chunking** — hierarchical parent-child chunking with overlap, enriched with course, document,
   section, page/slide, chunk id, and chunk type metadata.
5. **Indexing** — chunks are written to the QVAC workspace for the course. ChromaDB remains as a
   passive, disabled-by-default fallback path.

### 3.2 Query pipeline

A study request is routed by the dispatcher according to the action registry, which declares for
each action whether retrieval, generation, and source grounding are required. Retrieval produces
candidate chunks, which are deduplicated, boosted, reranked, token-budgeted, expanded to parent
context, and compressed into an evidence pack. Generation consumes the evidence pack's numbered
context block and emits `[ref_N]` markers that are parsed back into citations.

A semantic cache short-circuits repeated or near-identical queries. Every dispatch emits a
structured trace (retrieval ran, chunks found, generation ran, fallback used, duration) for
observability and debugging.

---

## 4. Known architectural tension

The platform currently contains **two parallel retrieval paths**:

- `study_service` — used by the study actions, performing dense retrieval against QVAC.
- `chat_service` — used by the conversational endpoint, implementing the full hybrid pipeline
  (dense + BM25 sparse, normalised fusion, cross-encoder reranking, MMR diversification, parent
  expansion).

The richer pipeline therefore currently serves the conversational endpoint rather than the study
actions, which are the product's core. Consolidating the two paths is tracked as planned
architectural work and is the highest-priority refactor in the roadmap.

---

## 5. Development pipeline

Work proceeds in a deliberate order, tracked as milestones on GitHub. The order matters and is not
the obvious one:

```
1. Testing        →  2. Persistence  →  3. Agent harness  →  4. Implementation completion
   (M2)               (M3)               (M4)                 (M5)
```

**Testing comes first.** The quality gate is established before any substantial code lands, so every
later phase merges through it. The alternative — integrating a large body of work and then building
the gate — means the largest, riskiest change is the one thing the gate never protected. This
project has already seen what an unenforced gate costs: CI was configured for branches that were not
the default branch, so nothing ran on `master` for weeks and nobody noticed.

**Persistence comes before the agent harness.** An agent that plans, generates, critiques and
repairs is expensive to run. Without durable memory, every repetition pays that cost again. Building
the harness first would mean building it against a memory model that is about to change.

**Implementation completion comes last.** The `mvp-testing` branch carries a large body of working,
tested code — quiz unification, the course builder, structured generation, the inference ladder.
Integrating it is sequenced last so it lands on top of the gate, the persistence layer and the agent
foundations, rather than underneath them.

Milestones M6–M9 (topic base, retrieval consolidation, assessment and exam prep, platform health)
follow, and are not strictly ordered relative to each other.

---

## 6. Documentation map

| Document | Contents |
|---|---|
| [`overview.md`](overview.md) | This document — vision, scope, architecture |
| [`specifications.md`](specifications.md) | Functional requirements with implementation status |
| [`agent-memory-plan.md`](agent-memory-plan.md) | Inference ladder, hardware tiers, and persistent student-memory roadmap |
| [`../AGENTS.md`](../AGENTS.md) | Contribution workflow, branching, PR and merge rules |
| [`../README.md`](../README.md) | Setup, configuration, testing, troubleshooting |
