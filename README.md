# BitPolito Academy

Open-source educational platform for Bitcoin study. Upload course materials (slides, PDFs, textbooks) and get AI-powered tutoring with source-anchored citations and 8 study actions: **explain**, **summarize**, **retrieve**, **open_questions**, **quiz**, **oral**, **derive**, **compare**.

---

## Quick start

### What you need

| Requirement | Version | Notes |
| --- | --- | --- |
| Node.js | ≥ 22.17 | Required by the QVAC SDK |
| Python | 3.11 | Backend and ingestion pipeline |
| uv | latest | Recommended — [install](https://docs.astral.sh/uv/getting-started/installation/) |
| Redis | ≥ 7 | Optional — enables background ingestion (`brew install redis`) |
| Disk | ≥ 4 GB | Embedding model ~670 MB + Qwen3-4B LLM ~2.5 GB (downloaded on first run) |
| RAM | ≥ 8 GB | ~5 GB in use at runtime; 16 GB recommended |

SQLite is used in development — no PostgreSQL needed.

### One-command start

```bash
chmod +x start-dev.sh
./start-dev.sh
```

This script installs dependencies, initialises the database, starts Redis and the background worker if available, then launches all three services. The first run downloads the AI models (2–5 minutes).

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:3000> |
| Backend API | <http://localhost:8000> |
| QVAC service | <http://localhost:3001> |
| API docs | <http://localhost:8000/docs> |

**Dev credentials (created automatically):**

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@bitpolito.it` | `DevAdmin@2024!Secure` |
| Student | `student@bitpolito.it` | `DevStudent@2024!Learn` |

### Manual start

```bash
# Frontend
cd apps/web && npm install && npm run dev

# Backend
cd services/ai
uv sync
uv run python -m app.db.init_db
uv run uvicorn app.main:app --reload --port 8000

# Background worker (optional — requires Redis)
redis-server --daemonize yes
cd services/ai && REDIS_URL=redis://localhost:6379/0 arq app.workers.arq_worker.WorkerSettings

# QVAC service (downloads models on first run)
cd workers/qvac-service && npm install && node src/server.js
```

> Set `QVAC_LLM_ENABLED=false` to skip loading the Qwen3-4B language model and run in retrieval-only mode (~670 MB instead of ~3.2 GB).

---

## How it works

### Uploading a document

When you upload a PDF, PPTX, or DOCX, the pipeline runs automatically:

```text
Upload
  → parse (text per page/slide)
  → clean (remove watermarks, headers, footers)
  → chunk into parent blocks (~1200 words) and child blocks (~150 words)
  → save parent blocks to the database
  → index child blocks in QVAC (dense vector store)
  → build / update the BM25 sparse index
```

Child blocks are the retrieval units. Parent blocks give the LLM wider context when generating answers.

### Answering a question

```text
Your question
  → dense search (QVAC, top 20 results)
  + sparse search (BM25 keyword index)
  → merge and re-rank with Reciprocal Rank Fusion
  → FlashRank cross-encoder rerank → top 5 child blocks
  → load the parent block for each result (1200-word context)
  → Qwen3-4B generates an answer with inline citations (p. N / Slide N)
```

If the QVAC service is unreachable, the system falls back to ChromaDB.

---

## Project layout

```text
bitcoin-academy/
├── apps/web/               Next.js 14 frontend
├── services/ai/            FastAPI backend
│   └── app/
│       ├── api/            REST endpoints
│       ├── workers/
│       │   ├── pipeline.py       document ingestion pipeline
│       │   └── arq_worker.py     background job definitions
│       ├── services/
│       │   ├── chat_service.py   hybrid RAG search and answer generation
│       │   └── study_service.py  8 study actions
│       └── db/
│           └── models.py         database schema (incl. ChunkParent table)
└── workers/qvac-service/   Node.js embedding + LLM service
    └── src/
        ├── server.js       HTTP routes
        ├── models.js       loads GTE-Large and Qwen3-4B
        ├── ingest.js       vector indexing
        └── query.js        retrieval and generation
```

---

## API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Create an account |
| `POST` | `/api/auth/login` | Log in → JWT |
| `GET` | `/api/courses` | List courses |
| `POST` | `/api/courses` | Create a course workspace |
| `POST` | `/api/courses/{id}/documents` | Upload a document |
| `POST` | `/api/courses/{id}/study` | AI study action (20 req/min) |
| `POST` | `/api/courses/{id}/chat` | Free-form RAG chat |
| `POST` | `/api/auth/refresh` | Refresh access token |
| `GET` | `/api/auth/me` | Get current user |
| `POST` | `/api/auth/logout` | Logout (blacklist token) |
| `GET` | `/api/courses/{id}` | Get a specific course |
| `GET` | `/api/courses/{id}/lessons` | List lessons for a course |
| `GET` | `/api/lessons/{id}` | Get a specific lesson |
| `GET` | `/api/courses/{id}/documents` | List documents for a course |
| `GET` | `/api/documents/{id}` | Get document detail |
| `GET` | `/api/documents/{id}/status` | Poll ingestion status |
| `GET` | `/api/documents/{id}/preview` | Preview document content |
| `DELETE` | `/api/documents/{id}` | Delete a document |
| `POST` | `/api/documents/{id}/reindex` | Re-index a document |
| `POST` | `/api/documents/{id}/retry` | Retry a failed ingestion |
| `GET` | `/api/progress/{id}` | Get course progress |
| `POST` | `/api/progress/update` | Update lesson progress |
| `GET` | `/api/badges` | List all badges |
| `GET` | `/api/badges/user` | Get current user's badges |
| `GET` | `/api/courses/{id}/quizzes` | List quizzes for a course |
| `GET` | `/api/quizzes/{quiz_id}` | Get a quiz |
| `POST` | `/api/quizzes/{quiz_id}/attempts` | Submit a quiz attempt |
| `GET` | `/api/users/me/certificates` | List user certificates |
| `GET` | `/api/certificates/verify/{code}` | Verify a certificate |
| `GET` | `/api/study/actions` | List available study actions |
| `GET` | `/health` | Health check |

Full interactive documentation at `http://localhost:8000/docs`.

---

## Configuration

**Backend** (`services/ai/.env`):

```env
DATABASE_URL=sqlite:///./bitcoin_academy.db
SECRET_KEY=<random 32+ chars>
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000

QVAC_SERVICE_URL=http://localhost:3001
QVAC_INGEST_DIR=./qvac_ingest
QVAC_INGEST_TIMEOUT=300

REDIS_URL=redis://localhost:6379/0   # optional

RAG_RETRIEVE_K=20    # candidates fetched before reranking
RAG_TOP_K=5          # results passed to the LLM

SKIP_CHROMA_INDEX=true
LOG_LEVEL=INFO
```

**QVAC service**:

```env
QVAC_PORT=3001
QVAC_INGEST_DIR=./qvac_ingest   # must match backend setting
QVAC_LLM_ENABLED=true           # set to false for retrieval-only mode
```

**Frontend** (`apps/web/.env.local`):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXTAUTH_SECRET=dev-secret-key
NEXTAUTH_URL=http://localhost:3000
```

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 14 · TypeScript · Tailwind CSS |
| Backend | FastAPI · SQLAlchemy 2 · Pydantic v2 · uv |
| Parsing | pymupdf4llm · python-pptx · python-docx |
| Chunking | Parent-child: 1200-word context blocks → 150-word retrieval blocks |
| Vector search | QVAC HyperDB (dense) + BM25 (sparse) → RRF merge → FlashRank rerank |
| Embedding | GTE-Large FP16 (1024-dim, via QVAC) |
| Language model | Qwen3-4B Q4\_K\_M (local, CPU/MPS, via QVAC) |
| Task queue | arq + Redis (falls back to FastAPI BackgroundTasks) |
| Database | SQLite (dev) · PostgreSQL (prod) |

---

## Testing

### Backend (Python — pytest)

```bash
cd services/ai
uv run pytest                        # unit + integration, with coverage
uv run pytest tests/unit/            # unit tests only
uv run pytest tests/integration/     # integration tests only
uv run pytest -m "not integration"   # skip integration tests
```

Tests use an in-memory SQLite database and mock the QVAC service — no external services needed.

### Frontend (TypeScript — Jest)

```bash
cd apps/web
npm test             # run all tests with coverage
npm run test:watch   # watch mode
```

### QVAC service (Node.js)

```bash
cd workers/qvac-service
npm test
```

---

## License

MIT
