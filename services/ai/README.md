# Backend — FastAPI service

Python 3.11 · FastAPI · SQLAlchemy 2 · uv

## Setup

```bash
cd services/ai
uv sync
cp .env.example .env   # then fill in the required values
uv run python -m app.db.init_db
uv run uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Interactive documentation at `http://localhost:8000/docs`.

## Environment

See [`../../docs/configuration.md`](../../docs/configuration.md) for all variables. Minimum required:

```env
DATABASE_URL=sqlite:///./bitcoin_academy.db
SECRET_KEY=<random 32+ chars>
ENVIRONMENT=development
```

## Testing

```bash
uv run pytest                       # all tests (unit + integration)
uv run pytest tests/unit/           # unit tests only
uv run pytest tests/integration/    # integration tests only
uv run pytest -m "not integration"  # skip integration tests
```

Tests use an in-memory SQLite database and mock the QVAC service — no external services required.

## Structure

See [`../../docs/architecture.md`](../../docs/architecture.md) for the full project layout and component overview.
