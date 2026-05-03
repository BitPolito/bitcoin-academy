# BitPolito Academy

Open-source educational platform for Bitcoin study. Turns course materials (slides, textbooks, past exams) into an AI workspace with RAG tutoring, source-anchored citations, and 8 study actions.

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Node.js | **≥ 22.17** | Required by `@qvac/sdk` (bare runtime shims) |
| Python | 3.11 | FastAPI backend and ingestion pipeline |
| Disk | ~2 GB | QVAC embedding model (~670 MB, downloaded on first run) |
| RAM | ≥ 8 GB | For local LLM inference (optional) |

> No PostgreSQL needed in development: the backend uses **SQLite** (`services/ai/bitcoin_academy.db`).

### Start

```bash
chmod +x start-dev.sh
./start-dev.sh
```

The script creates the Python virtualenv, installs all dependencies, waits for the backend and QVAC service to be healthy, seeds the database with test users, then starts the frontend.

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

# Backend
cd services/ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.db.init_db          # create DB and seed users
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
│       ├── workers/pipeline.py      # parse → chunk → ChromaDB + QVAC (BackgroundTask)
│       ├── services/
│       │   ├── study_service.py     # dispatch 8 actions, DispatchTrace, QVAC /query
│       │   └── chat_service.py      # free chat → QVAC /query
│       ├── schemas/study_schemas.py # StudyAction enum (8), ActionMeta, STUDY_ACTION_REGISTRY
│       ├── core/rate_limit.py       # slowapi Limiter singleton
│       └── db/                      # SQLAlchemy models, session, init_db
├── workers/
│   ├── python-ingester/src/         # RamSafeIngestor, StructuralParser, Chunker (used by pipeline.py)
│   │                                # + main_ingester_pipeline.py (CLI ingestion path)
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
| Backend | FastAPI · SQLAlchemy 2 · Pydantic v2 · python-jose · slowapi |
| Vector store | ChromaDB (ingestion) + QVAC HyperDB (query) |
| Embedding | fastembed `all-MiniLM-L6-v2` (pipeline) · QVAC `GTE_LARGE_FP16` (query) |
| LLM | LangChain + OpenAI (optional) · QVAC raw answer as fallback |
| QVAC service | Node.js 22.17+ · `@qvac/sdk` |
| Database | SQLite (dev) · PostgreSQL (prod) |

---

## Ingestion flow

```
Upload via UI
        │
        ▼
pipeline.py (BackgroundTask)
  │
  ├─ RamSafeIngestor      → RAM-safe batch reader (PDF/PPTX)
  ├─ StructuralParser     → pdfplumber + Docling ML → normalized blocks
  ├─ Chunker              → 3 levels: section / paragraph / micro
  ├─ fastembed + ChromaDB → paragraph chunks → persistent vector store
  ├─ Write *_contingency.jsonl to QVAC_INGEST_DIR
  └─ POST :3001/ingest    → QVAC ragIngest → HyperDB workspace

CLI path: workers/python-ingester/src/main_ingester_pipeline.py
```

Documents are indexed in **both** systems:
- **ChromaDB** — used by debug endpoints (`/api/debug/*`)
- **QVAC HyperDB** — used by `/api/courses/{id}/study` and `/api/courses/{id}/chat`

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
UPLOADS_DIR=./uploads
CHROMA_DB_PATH=./chroma_db
CHROMA_COLLECTION_NAME=bitpolito_course

RAG_TOP_K=5
RAG_MAX_EVIDENCE=6
LLM_TIMEOUT_SECONDS=30

OPENAI_API_KEY=          # optional — enables LLM generation
DEBUG_MODE=false
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
