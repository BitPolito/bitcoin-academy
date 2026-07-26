# BitPolito Academy

[![CI](https://github.com/BitPolito/bitcoin-academy/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/BitPolito/bitcoin-academy/actions/workflows/ci.yml)

Educational platform for Bitcoin study built at BitPolito. Upload slides, PDFs, or textbooks and interact with them through eight study actions: **explain**, **summarize**, **retrieve**, **open\_questions**, **quiz**, **oral**, **derive**, **compare**.

Everything runs locally — no external API keys needed. The retrieval pipeline uses QVAC dense search (GTE-Large FP16) combined with BM25, cross-encoder reranking, MMR diversity, and optional Qwen3-4B for answer generation. A semantic cache (fastembed + Redis) avoids recomputing identical or near-identical queries.

---

## Requirements

| Dependency | Version |
|---|---|
| Node.js | ≥ 22.17 |
| Python | 3.11 |
| uv | latest |
| Redis | ≥ 7 |

Redis is optional in development but required in production for background ingestion, semantic cache, token blacklist, and account lockout. SQLite is used in development — no PostgreSQL setup needed.

**Disk and RAM:** plan for ~4 GB of disk (embedding model ~670 MB + Qwen3-4B ~2.5 GB, downloaded on first run) and at least 8 GB RAM (~5 GB at runtime with the LLM loaded). 16 GB is more comfortable.

If you're on a machine with less than 8 GB free, set `QVAC_LLM_ENABLED=false`. The system will run in retrieval-only mode (~670 MB total): all study actions still return source passages, but there's no prose generation.

---

## Quick Start (Docker)

```bash
# 1. Create root .env with database credentials
echo "DATABASE_URL=postgresql://bitcoin_academy:bitcoin_academy@postgres:5432/bitcoin_academy" > .env

# 2. Copy and configure service env files
cp services/ai/.env.example services/ai/.env
cp apps/web/.env.example     apps/web/.env.local

# 3. Start everything
docker compose up --build
```

`docker compose up` automatically merges `docker-compose.yml` with `docker-compose.override.yml`, which adds source mounts, hot reload, and exposed ports. To run the production base without the dev overrides:

```bash
docker compose -f docker-compose.yml up --build
```

| Service | Dev URL |
|---|---|
| Frontend | http://localhost:3000 (through Caddy on :80 in prod) |
| Backend API | http://localhost:8000 (through Caddy on /api/* in prod) |
| Reverse proxy | http://localhost:80 |
| QVAC service | http://localhost:3001 |
| Interactive API docs | http://localhost:8000/docs (dev only) |

Default development accounts created automatically:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@bitpolito.it` | `DevAdmin@2024!Secure` |
| Student | `student@bitpolito.it` | `DevStudent@2024!Learn` |

---

## Manual Start (Development)

```bash
# Frontend
cd apps/web && npm install && npm run dev

# Backend — run setup once, then start the server
cd services/ai
cp .env.example .env          # fill in SECRET_KEY at minimum
bash setup-dev.sh             # installs deps, initialises DB, creates dev accounts
uv run uvicorn app.main:app --reload --port 8000

# Background worker (optional — requires Redis)
redis-server --daemonize yes
cd services/ai
uv run arq app.workers.arq_worker.WorkerSettings

# QVAC service (downloads models on first run — 2–5 minutes)
cd workers/qvac-service && npm install && node src/server.js
```

---

## Configuration

```bash
cp services/ai/.env.example services/ai/.env
cp apps/web/.env.example     apps/web/.env.local
```

Docker Compose also needs a root-level `.env` with `DATABASE_URL` (used in variable substitution — see the Docker quick start above).

Set `ENVIRONMENT=development` to enable Swagger UI and relaxed CORS.

### RAG variables

| Variable | Default | Description |
|---|---|---|
| `QVAC_SERVICE_URL` | `http://localhost:3001` | URL of the QVAC Node.js service |
| `QVAC_INGEST_DIR` | `./qvac_ingest` | Where the pipeline writes JSONL files for QVAC |
| `QVAC_INGEST_TIMEOUT` | `300` | Timeout (s) for the QVAC `/ingest` call |
| `RAG_TOP_K` | `5` | Chunks passed to the LLM after reranking |
| `RAG_RETRIEVE_K` | `20` | Candidates fetched from the dense + sparse pool |
| `RAG_MAX_CONTEXT_TOKENS` | `6000` | Token budget for context blocks |
| `RAG_MAX_EVIDENCE` | `6` | Max evidence chunks returned by the study endpoint |
| `RAG_HYDE` | `true` | Hypothetical Document Embedding query expansion |
| `RAG_QUERY_REWRITE` | `false` | Rewrite the raw question into a dense retrieval query |
| `RAG_COMPRESS_CONTEXT` | `true` | Trim each passage to relevant sentences before the LLM |
| `RAG_CONTEXTUAL_CHUNKS` | `false` | Prepend an AI-generated context prefix at ingest time |
| `RAG_SEMANTIC_CACHE` | `true` | Enable semantic cache (requires Redis) |
| `RAG_CACHE_THRESHOLD` | `0.92` | Cosine similarity threshold for a cache hit |
| `RAG_CACHE_TTL_SECONDS` | `86400` | Cache entry lifetime (24 h) |
| `USE_DOCLING` | `false` | Use Docling for PDF parsing instead of pymupdf4llm |
| `SKIP_CHROMA_INDEX` | `false` (`true` in `.env.example`) | Skip ChromaDB write during ingestion (QVAC-only mode) |

Full list: [`services/ai/.env.example`](services/ai/.env.example).

---

## Testing

```bash
# Backend (pytest)
cd services/ai
uv run pytest                       # all tests
uv run pytest tests/unit/
uv run pytest tests/integration/

# RAG end-to-end suite
uv run python test_rag.py                            # 35 curated queries
uv run python test_rag.py --query "What is Bitcoin?" # single query
uv run python test_rag.py --output results.json      # save JSON report

# Frontend
cd apps/web && npm test

# QVAC service
cd workers/qvac-service && npm test
```

The RAG suite runs 35 queries across 7 categories (basic, chapter, conceptual, comparative, synthesis, adversarial, stress) through the full retrieval pipeline, scoring each PASS / WARN / FAIL by retrieval confidence. Results are saved as JSON for baseline comparisons.

CI runs on every push and pull request to `master` via GitHub Actions (`.github/workflows/ci.yml`). See [`AGENTS.md`](AGENTS.md) for the contribution workflow.

---

## Docs

| Document | Contents |
|---|---|
| [`docs/overview.md`](docs/overview.md) | Vision, product scope, architecture, technical principles |
| [`docs/specifications.md`](docs/specifications.md) | Functional requirements with implementation status |
| [`AGENTS.md`](AGENTS.md) | Contribution workflow — branching, PRs, CI, merge rules |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| QVAC service fails to start | Model download timed out on first run | Re-run `node src/server.js` — models are cached after the first successful download |
| `/health` returns `database: disconnected` | `DATABASE_URL` missing or wrong | Check `services/ai/.env`; confirm PostgreSQL is running (or use the SQLite default for dev) |
| Document stuck in `processing` forever | Redis not running → ARQ worker not started | `redis-server --daemonize yes`, then start the ARQ worker |
| Frontend CORS error | `CORS_ORIGINS` missing the frontend origin | Add the frontend URL to `CORS_ORIGINS` in `services/ai/.env` |
| Chat returns "Il servizio di ricerca non è disponibile" | QVAC service not running | `cd workers/qvac-service && node src/server.js` |
| SSR API calls fail in Docker (`ECONNREFUSED localhost:8000`) | Next.js server-side calls resolve to the wrong host | `docker-compose.yml` sets `API_BASE_URL=http://api:8000/api` for SSR; make sure the web container env is current |

---

## License

MIT
