# Bitcoin Academy

An open-source, local-first platform for structured Bitcoin education. Transforms curated documents into guided courses with lessons, quizzes, progress tracking, and AI-assisted tutoring via a RAG pipeline.

## Table of Contents

- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Development](#development)
- [API](#api)
- [Contributing](#contributing)
- [License](#license)

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Node.js | **≥ 22.17** | Required by `@qvac/sdk` (bare runtime shims). |
| Python | 3.11 | For the FastAPI backend and ingestion pipeline. |
| PostgreSQL | any recent | Running and accessible. |
| Disk space | ~2 GB | For the QVAC embedding model (~670 MB) downloaded on first run. |
| RAM | ≥ 8 GB | For the default LLM when one is configured (see QVAC docs). |

### Recommended

```bash
chmod +x start-dev.sh
./start-dev.sh
```

This script creates a Python virtualenv under `services/ai/venv/`, installs dependencies for both services, seeds the database with test users, and starts both servers.

| Service        | URL                        |
|----------------|----------------------------|
| Frontend       | <http://localhost:3000>    |
| Backend API    | <http://localhost:8000>    |
| QVAC service   | <http://localhost:3001>    |
| Swagger UI     | <http://localhost:8000/docs>  |
| ReDoc          | <http://localhost:8000/redoc> |

> Swagger UI and ReDoc are only available in `development` environment.

**Dev credentials (seeded automatically):**

| Role    | Email                | Password              |
|---------|----------------------|-----------------------|
| Admin   | admin@bitpolito.it   | DevAdmin@2024!Secure  |
| Student | student@bitpolito.it | DevStudent@2024!Learn |

### Manual setup

**Frontend:**

```bash
cd apps/web
npm install
npm run dev
```

**Backend:**

```bash
cd services/ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**QVAC service** (Node.js — embedding + retrieval + optional LLM generation):

```bash
cd workers/qvac-service
npm install
node src/server.js
# Downloads the embedding model (~670 MB) on first run, then listens on :3001
```

---

## Project Structure

```text
bitcoin-academy/
├── apps/
│   └── web/                        # Next.js 14 frontend
│       ├── Dockerfile
│       └── src/
│           ├── app/                # App Router pages (auth, courses, dashboard, study)
│           ├── components/         # React components
│           └── lib/                # API client, auth helpers, services
├── services/
│   └── ai/                         # FastAPI backend
│       ├── Dockerfile
│       └── app/
│           ├── api/                # Route handlers (auth, chat, courses, documents, progress, quizzes, certificates)
│           ├── workers/
│           │   └── pipeline.py     # parse → chunk → ChromaDB + QVAC ingest (BackgroundTask)
│           ├── services/
│           │   └── chat_service.py # Forwards /chat queries to the QVAC service via httpx
│           ├── repositories/       # Data access layer
│           ├── db/                 # SQLAlchemy models and session
│           ├── schemas/            # Pydantic request/response models
│           ├── core/               # Config, DI container, error handling, token blacklist
│           └── middleware/         # Request ID, security headers
├── workers/
│   ├── python-ingester/            # Standalone Python ingestion pipeline (PDF/PPTX → JSONL)
│   │   └── src/
│   │       ├── module_1_ingestor.py   # RamSafeIngestor — RAM-safe PDF/PPTX batch reader
│   │       ├── module_2_parser.py     # StructuralParser — hybrid pdfplumber + Docling ML
│   │       ├── module_3_micro_chunker.py  # VerilocalChunker — 3-level chunking (section/paragraph/micro)
│   │       ├── module_4_exporter.py   # JsonlExporter — writes *_contingency.jsonl
│   │       ├── retrieval_*.py         # ChromaDB embedder + searcher + benchmark
│   │       └── main_ingester_pipeline.py  # CLI entry point
│   └── qvac-service/               # Node.js service — QVAC SDK (embedding + HyperDB + LLM)
│       └── src/
│           ├── models.js    # loadModel lifecycle (GTE_LARGE_FP16 embedding; LLM placeholder)
│           ├── ingest.js    # ragIngest — reads *_contingency.jsonl, indexes paragraph chunks
│           ├── query.js     # ragSearch + optional completion
│           └── server.js    # HTTP server on :3001 — POST /ingest, POST /query, GET /health
├── docs/
│   ├── qvac-integration.md         # Step-by-step guide for the QVAC SDK integration
│   └── src/                        # Source PDFs and PPTX used in tests
├── .github/
│   └── workflows/
│       └── ci.yml                  # CI: pytest + mypy + tsc + jest on every PR
├── docker-compose.yml
├── start-dev.sh
└── package.json                    # Root workspace (npm workspaces: apps/*, workers/qvac-service)
```

---

## Tech Stack

### Frontend (`apps/web`)

| Technology    | Role                         |
|---------------|------------------------------|
| Next.js 14    | React framework, App Router  |
| TypeScript    | Type safety                  |
| Tailwind CSS  | Styling                      |
| NextAuth.js 4 | Session-based authentication |
| Jest + RTL    | Unit and integration tests   |

### Backend (`services/ai`)

| Technology           | Role                                          |
|----------------------|-----------------------------------------------|
| FastAPI              | HTTP framework                                |
| SQLAlchemy 2         | ORM                                           |
| Pydantic v2          | Data validation and serialization             |
| python-jose + bcrypt | JWT authentication                            |
| httpx                | HTTP client — calls the QVAC service for chat |
| ChromaDB             | Vector store used during document ingestion   |
| fastembed            | Embedding during ingestion (all-MiniLM-L6-v2) |
| PostgreSQL           | Primary database                              |
| slowapi              | Rate limiting                                 |
| pytest               | Test suite                                    |

### QVAC service (`workers/qvac-service`)

| Technology    | Role                                                              |
|---------------|-------------------------------------------------------------------|
| Node.js 22.17+| Runtime                                                           |
| `@qvac/sdk`   | Local-first AI — embedding, HyperDB vector store, LLM generation |
| `node:test`   | Built-in test runner                                              |

### Document ingestion pipeline (`workers/python-ingester`)

| Technology         | Role                                              |
|--------------------|---------------------------------------------------|
| pdfplumber         | Primary PDF parser                                |
| Docling | ML-based parser — flag `--docling`                |
| python-pptx        | PPTX parser                                       |
| fastembed          | Paragraph-level embedding (all-MiniLM-L6-v2 ONNX) |
| ChromaDB           | Persistent vector store                           |

---

## Development

### Environment variables

**Backend** — create `services/ai/.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/bitcoin_academy
SECRET_KEY=your-secret-key
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000

# QVAC service (default: http://localhost:3001)
QVAC_SERVICE_URL=http://localhost:3001

# Directory where the pipeline writes JSONL files for QVAC ingestion
# (default: services/ai/qvac_ingest/)
QVAC_INGEST_DIR=/absolute/path/to/qvac_ingest

# ChromaDB path (default: services/ai/chroma_db/)
CHROMA_DB_PATH=/absolute/path/to/chroma_db
```

`DATABASE_URL` and `SECRET_KEY` are required at startup.

**QVAC service** — environment variables (optional):

```env
# Override the LLM model — any of the four modelSrc options in qvac-integration.md
# Default: QWEN3_4B_INST_Q4_K_M from the QVAC registry (~2.4 GB, requires ≥ 8 GB RAM)
# Leave unset to run without an LLM (embedding + retrieval only)
QVAC_LLM_SRC=/path/to/local/model.gguf

# Override the embedding model (default: GTE_LARGE_FP16, ~670 MB)
QVAC_EMB_SRC=

# Port (default: 3001)
QVAC_PORT=3001
```

**Frontend** — create `apps/web/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXTAUTH_SECRET=dev-secret-key
NEXTAUTH_URL=http://localhost:3000
```

### Commands

**Root (from `bitcoin-academy/`):**

```bash
npm run dev:web          # Start Next.js
npm run dev:api          # Start FastAPI via uvicorn
npm run test             # Run all tests
npm run type-check       # TypeScript + mypy
npm run lint             # ESLint
npm run format           # Prettier
```

**Backend only:**

```bash
cd services/ai
pytest                          # All tests (excludes slow)
pytest tests/unit -v            # Unit tests
pytest tests/integration        # Integration tests
pytest -m slow                  # Pipeline e2e (requires fastembed + chromadb)
mypy .
```

**QVAC service only:**

```bash
cd workers/qvac-service
npm test                        # node:test unit suite (no model download)
node src/server.js              # Start service — downloads models on first run
```

**Ingestion pipeline (CLI):**

```bash
cd workers/python-ingester
# Index a document into both ChromaDB and QVAC (QVAC service must be running)
python src/main_ingester_pipeline.py lecture.pdf \
  --course-id BTC_2025 --lecture-id L01 --docling
```

### Document ingestion flow

```
Upload via API                   CLI (direct)
       │                              │
       ▼                              ▼
pipeline.py (BackgroundTask)    main_ingester_pipeline.py
  │
  ├─ RamSafeIngestor + StructuralParser (PDF/PPTX → blocks)
  ├─ VerilocalChunker (section / paragraph / micro)
  ├─ fastembed + ChromaDB (paragraph chunks → vector store)
  ├─ Write *_contingency.jsonl to QVAC_INGEST_DIR
  └─ POST http://localhost:3001/ingest  ←── QVAC service
                                              └─ ragIngest → HyperDB workspace
```

### Chat query flow

```
Student question
  → POST /api/courses/{id}/chat  (FastAPI, JWT required)
  → chat_service.py
  → POST http://localhost:3001/query  (QVAC service)
        └─ ragSearch (HyperDB) → optional LLM completion
  → ChatResponse { answer, citations: [{snippet, score}], retrieval_used }
```

---

## API

All routers registered in `services/ai/app/main.py`:

| Prefix                        | Description                         |
|-------------------------------|-------------------------------------|
| `/api/auth`                   | Registration, login, JWT refresh    |
| `/api/courses/{id}/chat`      | RAG-backed Q&A (QVAC service)       |
| `/api/courses`                | Course CRUD and lesson listing      |
| `/api/courses/{id}/documents` | PDF/PPTX upload and indexing        |
| `/api/users/me/...`           | Progress tracking and certificates  |
| `/api/quizzes`                | Quiz placeholders (not yet active)  |
| `/health`                     | Health check with DB ping           |

Full interactive reference: `http://localhost:8000/docs` (development only).

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'feat: description'`
4. Push and open a Pull Request

**Guidelines:**

- TypeScript for frontend, Python for backend, JavaScript (ESM) for the QVAC service
- Run `npm run type-check`, `pytest`, and `npm test` (in `workers/qvac-service`) before opening a PR
- Node.js ≥ 22.17 is required — earlier versions will fail on `import "@qvac/sdk"`
- Update this README if you change the project structure, add new routes, or modify the startup sequence

---

## License

MIT
