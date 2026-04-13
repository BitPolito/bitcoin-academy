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

- Node.js 18+
- Python 3.10+
- PostgreSQL (running and accessible)

### Recommended

```bash
chmod +x start-dev.sh
./start-dev.sh
```

This script creates a Python virtualenv under `services/ai/venv/`, installs dependencies for both services, seeds the database with test users, and starts both servers.

| Service       | URL                                          |
|---------------|----------------------------------------------|
| Frontend      | <http://localhost:3000>                      |
| Backend API   | <http://localhost:8000>                      |
| Swagger UI    | <http://localhost:8000/docs>                 |
| ReDoc         | <http://localhost:8000/redoc>                |

> Swagger UI and ReDoc are only available in `development` environment.

**Dev credentials (seeded automatically):**

| Role    | Email                      | Password              |
|---------|----------------------------|-----------------------|
| Admin   | admin@bitpolito.it         | DevAdmin@2024!Secure  |
| Student | student@bitpolito.it       | DevStudent@2024!Learn |

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
│   └── ai/                         # FastAPI backend (primary service)
│       ├── Dockerfile
│       └── app/
│           ├── api/                # Route handlers (auth, courses, documents, progress)
│           ├── workers/            # Document processing pipeline
│           │   └── pipeline.py     # parse → chunk → embed → index (runs as BackgroundTask)
│           ├── services/           # Business logic
│           ├── repositories/       # Data access layer
│           ├── db/                 # SQLAlchemy models and session
│           ├── rag/                # LangChain RAG pipeline (chains, retrievers, prompts)
│           ├── schemas/            # Pydantic request/response models
│           ├── core/               # Config, DI container, error handling, token blacklist
│           └── middleware/         # Request ID, security headers
├── workers/                        # Standalone pipeline script (reference / CLI testing)
│   └── main.py
├── docs/
│   └── examples/
│       └── prototype/              # Original in-memory API prototype (reference only)
├── .github/
│   └── workflows/
│       └── ci.yml                  # CI: pytest + mypy + tsc + jest on every PR
├── docker-compose.yml              # Full stack: postgres + api + web
├── start-dev.sh                    # Dev startup script (no Docker required)
└── package.json                    # Root workspace (npm workspaces: apps/*, services/*)
```

---

## Tech Stack

### Frontend (`apps/web`)

| Technology     | Role                          |
|----------------|-------------------------------|
| Next.js 14     | React framework, App Router   |
| TypeScript     | Type safety                   |
| Tailwind CSS   | Styling                       |
| NextAuth.js 4  | Session-based authentication  |
| Jest + RTL     | Unit and integration tests    |

### Backend (`services/ai`)

| Technology          | Role                                    |
|---------------------|-----------------------------------------|
| FastAPI             | Async HTTP framework                    |
| SQLAlchemy 2        | ORM                                     |
| Pydantic v2         | Data validation and serialization       |
| python-jose + bcrypt| JWT authentication                      |
| LangChain + OpenAI  | RAG pipeline for AI tutoring            |
| PostgreSQL          | Primary database                        |
| slowapi             | Rate limiting                           |
| pytest              | Test suite                              |

---

## Development

### Environment variables

**Backend** — create `services/ai/.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/bitcoin_academy
SECRET_KEY=your-secret-key
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000
```

`DATABASE_URL` and `SECRET_KEY` are required at startup — the app will crash without them.

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
mypy .                   # Type checking
pytest                   # All tests
pytest tests/unit -v     # Unit tests with coverage
pytest tests/integration # Integration tests
```

---

## API

Registered routers in `services/ai/app/main.py`:

| Prefix       | Description                  |
|--------------|------------------------------|
| `/auth`      | Registration, login, JWT     |
| `/courses`   | Course CRUD                  |
| `/documents` | PDF upload and indexing      |
| `/progress`  | User progress tracking       |
| `/health`    | Health check with DB ping    |

> **Implemented but not yet registered:** `quizzes_api.py`, `chat_api.py`, `certificates_api.py` exist in `app/api/` but are not included in `app/main.py`.

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'feat: description'`
4. Push and open a Pull Request

**Guidelines:**

- TypeScript for frontend, Python for backend
- Run `npm run type-check` and `pytest` before opening a PR
- Update this README if you change the project structure or add new routes

---

## License

MIT
