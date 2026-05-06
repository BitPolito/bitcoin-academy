# BitPolito Academy

Open-source educational platform for Bitcoin study. Turns course materials (slides, textbooks, past exams) into an AI workspace with RAG tutoring, source-anchored citations, and 8 study actions.

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Node.js | **≥ 22.17** | Required by `@qvac/sdk` (bare runtime shims) |
| Python | **3.11** | FastAPI backend and ingestion pipeline |
| uv | latest | Recommended package manager — [install](https://docs.astral.sh/uv/getting-started/installation/) |
| Disk | ~2 GB | QVAC embedding model (~670 MB, downloaded on first run) |
| RAM | ≥ 8 GB | For local LLM inference (optional) |

> No PostgreSQL needed in development: the backend uses **SQLite** (`services/ai/bitcoin_academy.db`).

### Start

```bash
chmod +x start-dev.sh
./start-dev.sh
```

The script:
- **With uv** (recommended): runs `uv sync` — near-instant when the lockfile is unchanged
- **Without uv**: uses pip with a hash-check to skip installs when `requirements.txt` hasn't changed
- Starts QVAC and backend in background, runs their health checks in parallel
- Seeds the database with test users, then starts the Next.js frontend

| Service | URL |
|---|---|
| Frontend | <http://localhost:3000> |
| Backend API | <http://localhost:8000> |
| QVAC service | <http://localhost:3001> |
| Swagger UI | <http://localhost:8000/docs> |

**Development credentials (seeded automatically):**

| Role | Email | Password |
|---|---|---|
| Admin | `admin@bitpolito.it` | `DevAdmin@2024!Secure` |
| Student | `student@bitpolito.it` | `DevStudent@2024!Learn` |

### Manual start

```bash
# Frontend
cd apps/web && npm install && npm run dev

# Backend (with uv — recommended)
cd services/ai
uv sync                            # creates .venv and installs deps from uv.lock
uv run python -m app.db.init_db    # create DB and seed users
uv run uvicorn app.main:app --reload --port 8000

# Backend (with pip)
cd services/ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.db.init_db
python -m uvicorn app.main:app --reload --port 8000

# QVAC service
cd workers/qvac-service && npm install && node src/server.js
```

---

## Project structure

```
bitcoin-academy/
├── apps/web/                        # Next.js 14 — App Router
│   └── src/
│       ├── app/
│       │   ├── (auth)/              # Login / signup
│       │   ├── dashboard/           # Student dashboard (progress, completed courses)
│       │   └── courses/
│       │       ├── page.tsx         # Courses home — hero, stats, card grid
│       │       ├── layout.tsx       # TopBar + ToastProvider for all /courses/*
│       │       └── [courseId]/
│       │           ├── page.tsx     # Workspace — upload, doc list, detail panel
│       │           ├── study/       # Study — split-pane, 8 AI actions, evidence drawer
│       │           ├── debug/       # Pipeline visibility (dev only)
│       │           └── documents/[documentId]/preview/  # SourceViewer 3-pane
│       ├── components/
│       │   ├── ui/                  # BrandMark, TopBar, Toast, BadgeDisplay, ProgressBar
│       │   ├── courses/             # CourseCard, CreateCourseModal
│       │   ├── documents/           # DocumentUpload, DocumentRow
│       │   └── study/               # OutputPane, SourcePane, StudyActionBar, StudyOutput,
│       │                            # CitationCard, LessonNav, ContentChunks, SplitPane
│       └── lib/
│           ├── api/                 # apiFetch, documents API, types, adapters
│           └── services/            # courses, chat, study, progress
├── services/ai/                     # FastAPI backend
│   └── app/
│       ├── api/                     # auth, chat, courses, documents, study, debug, progress
│       ├── workers/pipeline.py      # parse → chunk → JSONL → QVAC /ingest (BackgroundTask)
│       ├── services/
│       │   ├── study_service.py     # dispatch 8 actions, DispatchTrace, QVAC /query
│       │   └── chat_service.py      # free chat → QVAC /query, ChromaDB fallback
│       ├── schemas/study_schemas.py # StudyAction enum (8), ActionMeta, STUDY_ACTION_REGISTRY
│       ├── core/rate_limit.py       # slowapi Limiter singleton
│       └── db/                      # SQLAlchemy models, session, init_db
├── workers/
│   ├── python-ingester/src/         # legacy — RamSafeIngestor, StructuralParser, Chunker (no longer used by pipeline.py)
│   └── qvac-service/src/            # Node.js — POST /ingest, POST /query, GET /health
├── docs/
│   ├── qvac-integration.md
│   ├── mvp-issues.md                # Open issues and gaps (P1/P2/post-MVP)
│   └── src/                         # Sample documents for testing (PDF, PPTX)
├── start-dev.sh                     # Full dev start with health check loop
└── docker-compose.yml
```

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 · TypeScript · Tailwind CSS · NextAuth.js 4 |
| Design system | BitPolito blue `#001CE0` · JetBrains Mono · `darkMode: 'class'` |
| Backend | FastAPI · SQLAlchemy 2 · Pydantic v2 · python-jose · slowapi · uv |
| Parsing | `pymupdf4llm` (PDF) · `python-pptx` (PPTX) · `python-docx` (DOCX) |
| Chunking | `chonkie` TokenChunker (512 tokens, 64 overlap) |
| Vector store | QVAC HyperDB (primary) · ChromaDB (passive fallback at query time) |
| Embedding | QVAC `GTE_LARGE_FP16` 1024-dim (ingestion + query) · fastembed `all-MiniLM-L6-v2` (ChromaDB fallback only) |
| LLM | LangChain + OpenAI (optional) · QVAC raw answer as fallback |
| QVAC service | Node.js 22.17+ · `@qvac/sdk` |
| Database | SQLite (dev) · PostgreSQL (prod) |

---

## Ingestion flow

```
Upload PDF / PPTX / DOCX via UI
        │
        ▼
pipeline.py (BackgroundTask)
  │
  ├─ parse_pdf()    → pymupdf4llm.to_markdown() → structured Markdown
  ├─ parse_pptx()   → python-pptx → Markdown with per-slide headings
  ├─ parse_docx()   → python-docx → Markdown with heading levels
  ├─ chunk_text()   → chonkie TokenChunker (512 tok, 64 overlap) → paragraph chunks
  ├─ _write_jsonl() → writes {doc_id}_contingency.jsonl to QVAC_INGEST_DIR
  └─ POST :3001/ingest (timeout 300s) → QVAC GTE_LARGE_FP16 → HyperDB workspace
```

**ChromaDB** is not written during ingestion (`SKIP_CHROMA_INDEX=true`).  
It remains as a passive fallback in `chat_service.py` if QVAC is unreachable.

## Study flow

```
Student: query + action (explain / summarize / retrieve / open_questions /
                          quiz / oral / derive / compare)
  → POST /api/courses/{id}/study  [rate limit: 20/min, JWT required]
  → study_service.dispatch()
      ├─ _retrieve()  → POST :3001/query → QVAC (embedding + HyperDB search)
      └─ _generate()  → LangChain + OpenAI (if OPENAI_API_KEY is set)
                        fallback: QVAC raw answer
  → StudyDispatchResponse { answer, citations, retrieval_used, action }
     + DispatchTrace JSON in logs (request_id, duration_ms, chunks_found, …)
```

---

## API

| Endpoint | Description |
|---|---|
| `POST /api/auth/register` | Register a new user |
| `POST /api/auth/login` | Login → JWT |
| `GET /api/courses` | List courses |
| `POST /api/courses` | Create a course workspace |
| `POST /api/courses/{id}/documents` | Upload a document (starts pipeline) |
| `POST /api/courses/{id}/study` | RAG study action — 20 req/min |
| `POST /api/courses/{id}/chat` | Free RAG chat |
| `GET /api/courses/{id}/documents/{doc_id}/preview` | SourceViewer data |
| `GET /api/debug/*` | Pipeline visibility endpoints (dev only) |
| `GET /api/health` | Health check |

Interactive docs: `http://localhost:8000/docs`

---

## Environment variables

**Backend** (`services/ai/.env`):

```env
DATABASE_URL=sqlite:///./bitcoin_academy.db
SECRET_KEY=<random 32+ chars>
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000

QVAC_SERVICE_URL=http://localhost:3001
QVAC_INGEST_DIR=./qvac_ingest
QVAC_INGEST_TIMEOUT=300      # seconds to wait for QVAC embedding (large PDFs need ~3-5 min)
UPLOADS_DIR=./uploads
CHROMA_DB_PATH=./chroma_db
CHROMA_COLLECTION_NAME=bitpolito_course
SKIP_CHROMA_INDEX=true       # skip in-process embedding; QVAC is the sole index

RAG_TOP_K=5
RAG_MAX_EVIDENCE=6
LLM_TIMEOUT_SECONDS=30

OPENAI_API_KEY=          # optional — enables LLM generation
DEBUG_MODE=false
LOG_LEVEL=INFO           # DEBUG for verbose output (sqlalchemy, httpx, etc.)
```

**Frontend** (`apps/web/.env.local`):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXTAUTH_SECRET=dev-secret-key
NEXTAUTH_URL=http://localhost:3000
```

---

## License

MIT
