# BitPolito Academy

Open-source educational platform for Bitcoin study. Upload course materials (slides, PDFs, textbooks) and interact with them through eight AI study actions: **explain**, **summarize**, **retrieve**, **open\_questions**, **quiz**, **oral**, **derive**, **compare**. All inference runs locally — no external API required.

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Node.js | ≥ 22.17 | Required by the QVAC SDK |
| Python | 3.11 | Backend and ingestion pipeline |
| uv | latest | [Installation guide](https://docs.astral.sh/uv/getting-started/installation/) |
| Redis | ≥ 7 | Optional in development (required in production for background ingestion, token blacklist, and account lockout) |
| Disk space | ≥ 4 GB | Embedding model ~670 MB + Qwen3-4B ~2.5 GB (downloaded on first run) |
| RAM | ≥ 8 GB | ~5 GB at runtime; 16 GB recommended |

SQLite is used in development — no PostgreSQL setup required.

---

## Quick Start

```bash
chmod +x start-dev.sh
./start-dev.sh
```

The script installs dependencies, initialises the database, starts Redis and the background worker if available, then launches all three services. The first run downloads the AI models (2–5 minutes).

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

## Manual Start

```bash
# 1. Frontend
cd apps/web && npm install && npm run dev

# 2. Backend
cd services/ai
uv sync
uv run python -m app.db.init_db
uv run uvicorn app.main:app --reload --port 8000

# 3. Background worker (optional — requires Redis)
redis-server --daemonize yes
cd services/ai
REDIS_URL=redis://localhost:6379/0 arq app.workers.arq_worker.WorkerSettings

# 4. QVAC service (downloads models on first run)
cd workers/qvac-service && npm install && node src/server.js
```

Set `QVAC_LLM_ENABLED=false` to skip loading the Qwen3-4B language model and run in retrieval-only mode (~670 MB instead of ~3.2 GB).

---

## Configuration

Copy the example files and edit the values before starting:

```bash
cp services/ai/.env.example services/ai/.env
cp apps/web/.env.example     apps/web/.env.local
```

**Docker Compose deployments** additionally require a root-level `.env` file (not committed) that sets `DATABASE_URL` with a secure password, since the compose file reads it via variable substitution:

```bash
# .env (at repository root)
DATABASE_URL=postgresql://user:strongpassword@postgres:5432/bitcoin_academy
```

Set `ENVIRONMENT=development` in the same file to restore development mode (Swagger UI, relaxed CORS).

See [`docs/configuration.md`](docs/configuration.md) for a complete description of every environment variable.

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

Tests use an in-memory SQLite database and mock the QVAC service — no external services required.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Project layout, tech stack, component overview |
| [`docs/api.md`](docs/api.md) | Full REST API reference |
| [`docs/rag-pipeline.md`](docs/rag-pipeline.md) | Ingestion pipeline and retrieval internals |
| [`docs/configuration.md`](docs/configuration.md) | All environment variables |

---

## License

MIT
