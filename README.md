# BitPolito Academy

[![CI](https://github.com/BitPolito/bitcoin-academy/actions/workflows/ci.yml/badge.svg?branch=rag)](https://github.com/BitPolito/bitcoin-academy/actions/workflows/ci.yml)

Open-source educational platform for Bitcoin study. Upload course materials (slides, PDFs, textbooks) and interact with them through eight AI study actions: **explain**, **summarize**, **retrieve**, **open\_questions**, **quiz**, **oral**, **derive**, **compare**.

All inference runs locally — no external API required. The RAG pipeline combines QVAC dense retrieval (GTE-Large FP16) with BM25 sparse search, cross-encoder reranking, MMR diversity selection, and optional streaming via Qwen3-4B. A semantic cache (fastembed + Redis) short-circuits repeated queries.

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Node.js | ≥ 22.17 | Required by the QVAC SDK |
| Python | 3.11 | Backend and ingestion pipeline |
| uv | latest | [Installation guide](https://docs.astral.sh/uv/getting-started/installation/) |
| Redis | ≥ 7 | Optional in development; required in production for background ingestion, semantic cache, token blacklist, and account lockout |
| Disk space | ≥ 4 GB | Embedding model ~670 MB + Qwen3-4B ~2.5 GB (downloaded on first run) |
| RAM | ≥ 8 GB | ~5 GB at runtime with LLM; 16 GB recommended |

> **8 GB RAM mode:** Set `QVAC_LLM_ENABLED=false` to skip loading Qwen3-4B. The system runs in retrieval-only mode (~670 MB total): it retrieves and surfaces the most relevant passages but does not generate prose answers. All study actions still return source excerpts.

SQLite is used in development — no PostgreSQL setup required.

---

## Quick Start (Docker)

```bash
# 1. Create root .env with database credentials
echo "DATABASE_URL=postgresql://bitcoin_academy:bitcoin_academy@postgres:5432/bitcoin_academy" > .env

# 2. Copy and configure service env files
cp services/ai/.env.example services/ai/.env
cp apps/web/.env.example     apps/web/.env.local

# 3. Start all services
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| QVAC service | http://localhost:3001 |
| Interactive API docs | http://localhost:8000/docs |

**Default development accounts (created automatically):**

| Role | Email | Password |
|---|---|---|
| Admin | `admin@bitpolito.it` | `DevAdmin@2024!Secure` |
| Student | `student@bitpolito.it` | `DevStudent@2024!Learn` |

---

## Manual Start (Development)

```bash
# 1. Frontend
cd apps/web && npm install && npm run dev

# 2. Backend — set up once, then start
cd services/ai
cp .env.example .env          # fill in SECRET_KEY at minimum
bash setup-dev.sh             # installs deps, initialises DB, creates dev accounts
uv run uvicorn app.main:app --reload --port 8000

# 3. Background worker (optional — requires Redis)
redis-server --daemonize yes
cd services/ai
uv run arq app.workers.arq_worker.WorkerSettings

# 4. QVAC service (downloads models on first run — 2–5 minutes)
cd workers/qvac-service && npm install && node src/server.js
```

Set `QVAC_LLM_ENABLED=false` to skip loading Qwen3-4B and run in retrieval-only mode.

---

## Configuration

Copy the example files and edit the values:

```bash
cp services/ai/.env.example services/ai/.env
cp apps/web/.env.example     apps/web/.env.local
```

**Docker Compose** additionally requires a root-level `.env` with `DATABASE_URL`, since the compose file reads it via variable substitution (see the Docker quick start above).

Set `ENVIRONMENT=development` to restore development mode (Swagger UI, relaxed CORS).

### Key RAG environment variables

| Variable | Default | Description |
|---|---|---|
| `QVAC_SERVICE_URL` | `http://localhost:3001` | URL of the QVAC Node.js service |
| `RAG_TOP_K` | `5` | Chunks passed to the LLM after reranking |
| `RAG_RETRIEVE_K` | `20` | Candidates fetched from dense + sparse pool |
| `RAG_MAX_CONTEXT_TOKENS` | `6000` | Token budget for context blocks |
| `RAG_HYDE` | `true` | Hypothetical Document Embedding query expansion |
| `RAG_COMPRESS_CONTEXT` | `true` | Compress context to query-relevant sentences |
| `RAG_CONTEXTUAL_CHUNKS` | `false` | AI-generated context prefix at ingest |
| `RAG_SEMANTIC_CACHE` | `true` | Enable semantic cache (requires Redis) |
| `RAG_CACHE_THRESHOLD` | `0.92` | Cosine similarity threshold for cache hit |
| `RAG_CACHE_TTL_SECONDS` | `86400` | Cache entry lifetime (24 h) |
| `USE_DOCLING` | `false` | Use Docling for PDF parsing instead of pymupdf4llm |
| `SKIP_CHROMA_INDEX` | `true` | Skip ChromaDB write during ingestion (QVAC-only) |

See [`docs/configuration.md`](docs/configuration.md) for the full list of variables.

---

## Testing

**Backend (pytest):**

```bash
cd services/ai
uv run pytest                       # all tests
uv run pytest tests/unit/           # unit tests only
uv run pytest tests/integration/    # integration tests only
```

**Frontend (Jest):**

```bash
cd apps/web && npm test
```

**QVAC service (Node.js):**

```bash
cd workers/qvac-service && npm test
```

CI runs automatically on every push and pull request to `main` and `rag` branches via GitHub Actions (`.github/workflows/ci.yml`).

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Project layout, tech stack, component overview |
| [`docs/api.md`](docs/api.md) | Full REST API reference |
| [`docs/configuration.md`](docs/configuration.md) | All environment variables |

> `docs/` is listed in `.gitignore` and is not committed to the repository.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| QVAC service fails to start | Model download timed out on first run | Re-run `node src/server.js`; models are cached after the first successful download |
| Backend starts but `/health` returns `database: disconnected` | `DATABASE_URL` not set or wrong | Check `services/ai/.env`; verify PostgreSQL is running (or use the SQLite default for dev) |
| Upload succeeds but document stays in `processing` state forever | Redis not running → ARQ worker not processing jobs | Start Redis: `redis-server --daemonize yes`; start ARQ worker (see Manual Start) |
| Frontend shows CORS error in browser | `CORS_ORIGINS` does not include the frontend origin | Add the frontend URL to `CORS_ORIGINS` in `services/ai/.env` |
| Chat returns "Il servizio di ricerca non è disponibile" | QVAC service is not running | Start the QVAC service: `cd workers/qvac-service && node src/server.js` |
| SSR API calls fail in Docker (`ECONNREFUSED localhost:8000`) | Next.js server-side rendering calls resolve to the wrong host | `docker-compose.yml` sets `API_BASE_URL=http://api:8000/api` for SSR; ensure the web container env is up to date |

---

## License

MIT
