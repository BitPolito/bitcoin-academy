# Backend — FastAPI service

Python 3.11 · FastAPI · SQLAlchemy 2 · uv

## Setup

```bash
cd services/ai
uv sync --locked --extra dev
cp .env.example .env   # then fill in the required values
uv run --no-sync python -m app.db.init_db
uv run --no-sync uvicorn app.main:app --reload --port 8000
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
uv sync --locked --extra dev                     # explicit, reproducible install
uv run --no-sync pytest                          # all tests (unit + integration)
uv run --no-sync pytest tests/unit/              # unit tests only
uv run --no-sync pytest tests/integration/       # integration tests only
uv run --no-sync pytest -m "not integration"     # skip integration tests
```

Tests use an in-memory SQLite database and mock the QVAC service — no external services required.
`--no-sync` guarantees that test execution never changes the environment or downloads packages;
run the locked sync explicitly whenever `uv.lock` changes.

## Structure

See [`../../docs/architecture.md`](../../docs/architecture.md) for the full project layout and component overview.
