# BitPolito Academy

[![CI](https://github.com/BitPolito/bitcoin-academy/actions/workflows/ci.yml/badge.svg?branch=rag)](https://github.com/BitPolito/bitcoin-academy/actions/workflows/ci.yml)

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

**Windows:** use `start.ps1` instead of `start.sh` (see [Windows Quick Start](#windows-quick-start) below), or use [Docker](#docker-full-stack) which works the same on all platforms.

**Disk and RAM:** plan for ~4 GB of disk (embedding model ~670 MB + Qwen3-4B ~2.5 GB, downloaded on first run) and at least 8 GB RAM (~5 GB at runtime with the LLM loaded). 16 GB is more comfortable.

If you're on a machine with less than 8 GB free, set `QVAC_LLM_ENABLED=false`. The system will run in retrieval-only mode (~670 MB total): all study actions still return source passages, but there's no prose generation.

---

## Quick Start

Uses SQLite — no Postgres or Redis needed to try the platform.

```bash
# 1. Copy env files (defaults work as-is for a local demo)
cp services/ai/.env.example services/ai/.env
cp apps/web/.env.example     apps/web/.env.local

# 2. First-time setup and start all services
./start.sh --setup
```

`--setup` installs dependencies, initialises the SQLite database, and creates the demo accounts.
On the first run QVAC downloads the embedding model (~670 MB) — expect 2–5 minutes before the
chat becomes available. You can monitor progress with:

```bash
tail -f .logs/qvac.log
```

Open **http://localhost:3000** and log in:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@bitpolito.it` | `DevAdmin@2024!Secure` |
| Student | `student@bitpolito.it` | `DevStudent@2024!Learn` |

> **Document ingestion** (uploading PDFs/slides) also requires Redis and the ARQ background worker.
> Start them separately if you want to test uploads:
> ```bash
> redis-server --daemonize yes
> cd services/ai && uv run arq app.workers.arq_worker.WorkerSettings
> ```

---

## Windows Quick Start

**Prerequisites:** [Node.js ≥ 22](https://nodejs.org), [Python 3.11](https://python.org/downloads), [uv](https://docs.astral.sh/uv/getting-started/installation/)

Open **PowerShell** (not cmd) in the project root. If you get an execution-policy error, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then:

```powershell
# 1. Copy env files
Copy-Item services\ai\.env.example  services\ai\.env
Copy-Item apps\web\.env.example     apps\web\.env.local

# 2. First-time setup and start all services
.\start.ps1 -Setup
```

This opens three separate PowerShell windows (frontend, backend, QVAC). Close them to stop all services. Subsequent runs: `.\start.ps1`.

> **Alternative:** [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/) (requires WSL2) gives you the exact same stack with a single command — see [Docker (full stack)](#docker-full-stack).

---

## Docker (full stack)

Runs Postgres, Redis, QVAC, API, frontend, and Caddy reverse proxy as containers.

```bash
# Copy env files
cp services/ai/.env.example services/ai/.env
cp apps/web/.env.example     apps/web/.env.local

# Create root .env with the Postgres URL used by docker-compose variable substitution
echo "DATABASE_URL=postgresql://bitcoin_academy:bitcoin_academy@postgres:5432/bitcoin_academy" > .env

# Start (dev mode — hot reload, ports exposed)
docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml up --build
```

> **First run:** QVAC downloads the embedding model (~670 MB) before it becomes healthy.
> The `api` and `arq-worker` services wait for QVAC — allow up to 5 minutes.
> Monitor with: `docker compose logs -f qvac`

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Reverse proxy (Caddy) | http://localhost:80 |
| QVAC service | http://localhost:3001 |
| Swagger UI | http://localhost:8000/docs |

Production base only (no dev overrides):
```bash
docker compose -f infra/docker-compose.yml up --build
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
| `SKIP_CHROMA_INDEX` | `true` | Skip ChromaDB write during ingestion (QVAC-only mode) |

Full list: [`docs/configuration.md`](docs/configuration.md).

---

## Testing

```bash
# Backend (pytest)
cd services/ai
uv run pytest                       # all tests
uv run pytest tests/unit/
uv run pytest tests/integration/

# RAG end-to-end suite
uv run python tests/test_rag.py                            # 35 curated queries
uv run python tests/test_rag.py --query "What is Bitcoin?" # single query
uv run python tests/test_rag.py --output results.json      # save JSON report

# Frontend
cd apps/web && npm test

# QVAC service
cd workers/qvac-service && npm test
```

The RAG suite runs 35 queries across 7 categories (basic, chapter, conceptual, comparative, synthesis, adversarial, stress) through the full retrieval pipeline, scoring each PASS / WARN / FAIL by retrieval confidence. Results are saved as JSON for baseline comparisons.

CI runs on every push and pull request to `main` and `rag` via GitHub Actions (`.github/workflows/ci.yml`).

---

## Docs

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Project layout, tech stack, component overview |
| [`docs/api.md`](docs/api.md) | Full REST API reference |
| [`docs/configuration.md`](docs/configuration.md) | All environment variables |

> `docs/` is in `.gitignore` and not committed to the repo.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `localhost:3000` — connection refused | Services not started, or `.env.local` missing | Run the two `cp` commands in Quick Start, then `./start.sh` (or `./start.sh --setup` on first run) |
| Port 3000 occupied by a stale process | Previous run exited without cleanup | `./start.sh` kills stale processes automatically; if running manually: `kill $(lsof -ti :3000)` |
| QVAC service fails to start | Model download timed out on first run | Re-run `node src/server.js` — models are cached after the first successful download |
| `/health` returns `database: disconnected` | `DATABASE_URL` missing or wrong | Check `services/ai/.env`; confirm PostgreSQL is running (or use the SQLite default for dev) |
| Document stuck in `processing` forever | Redis not running → ARQ worker not started | `redis-server --daemonize yes`, then start the ARQ worker |
| Frontend CORS error | `CORS_ORIGINS` missing the frontend origin | Add the frontend URL to `CORS_ORIGINS` in `services/ai/.env` |
| Chat returns "Il servizio di ricerca non è disponibile" | QVAC service not running | `cd workers/qvac-service && node src/server.js` |
| SSR API calls fail in Docker (`ECONNREFUSED localhost:8000`) | Next.js server-side calls resolve to the wrong host | `infra/docker-compose.yml` sets `API_BASE_URL=http://api:8000/api` for SSR; make sure the web container env is current |
| `start.sh` fails on Windows | bash not available | Use `.\start.ps1` in PowerShell, or run Docker (works on all platforms) |
| `execution of scripts is disabled` (PowerShell) | Execution policy blocks unsigned scripts | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |

---

## License

MIT
