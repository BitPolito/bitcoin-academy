# BitPolito Academy

BitPolito Academy is a local-first, open-source platform that provides a structured and interactive way to learn about Bitcoin.
It transforms curated documents into guided courses with lessons, quizzes, and progress tracking.
The goal is to make complex topics like cryptography and the Lightning Network accessible and engaging for students.
Each learning path is transparent, verifiable, and supported by AI tutoring.

## Table of Contents

- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Development](#development)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)
- [License](#license)


## Quick Start


### Prerequisites

- **Node.js** 18+ (frontend)
- **Python** 3.10+ (backend)
- **npm** or **yarn**
- **pip** or **poetry**

### Recommended setup

To start the full development environment, use the script:

```bash
chmod +x start-dev.sh
./start-dev.sh
```

This script installs dependencies and starts both the frontend (Next.js) and backend (FastAPI) in development mode.

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8000](http://localhost:8000)
- API Docs (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
- API Docs (ReDoc): [http://localhost:8000/redoc](http://localhost:8000/redoc)

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
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

## Project Structure



### Project structure (Monorepo)

```text
bitcoin-academy/
├── apps/
│   └── web/                    # Next.js frontend
│       ├── src/
│       │   ├── app/            # App Router pages
│       │   ├── lib/            # Utilities and services
│       │   └── components/     # React components
│       ├── __tests__/          # Unit and integration tests
│       ├── config/             # Configurations
│       ├── docs/               # Documentation
│       ├── .dockerignore
│       ├── jest.config.js
│       ├── jest.setup.js
│       ├── next.config.js
│       ├── postcss.config.js
│       ├── tailwind.config.js
│       ├── tsconfig.json
│       └── package.json
├── services/
│   └── ai/                     # FastAPI backend
│       ├── app/
│       │   ├── api/            # API controllers
│       │   ├── services/       # Business logic
│       │   ├── repositories/   # Data access
│       │   ├── db/             # Database models
│       │   ├── core/           # Core utilities
│       │   ├── middleware/     # HTTP middleware
│       │   ├── rag/            # LangChain pipelines
│       │   ├── schemas/        # Pydantic models
│       │   ├── main.py
│       │   └── api_deps.py
│       ├── config/             # Configurations
│       ├── docs/               # Documentation
│       ├── tests/              # Unit and integration tests
│       ├── .dockerignore
│       ├── mypy.ini
│       ├── pytest.ini
│       ├── pyproject.toml
│       ├── requirements.txt
│       └── setup.cfg
├── .github/                    # GitHub workflows
├── .eslintrc.json
├── .prettierrc.json
├── .prettierignore
├── .gitignore
├── .env.example
├── start-dev.sh                # Quick start script
├── README.md
└── package.json
```

## Tech Stack




### Frontend

- **Next.js 14** - React framework with App Router
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Styling
- **NextAuth.js** - Authentication
- **React 18** - UI library

### Backend

- **FastAPI** - Modern async Python web framework
- **SQLAlchemy** - ORM for database
- **Pydantic** - Data validation
- **LangChain** - RAG orchestration
- **PostgreSQL** - Database (recommended)

## Development



### Quick start for both services

```bash
./start-dev.sh
```

Or manually in two separate terminals:

```bash
# Terminal 1 - Frontend
cd apps/web
npm run dev

# Terminal 2 - Backend
cd services/ai
python -m uvicorn app.main:app --reload
```

> **Note**: Ensure that the backend FastAPI application is properly configured in `services/ai/app/main.py` with all necessary routes and middleware setup.



### Useful commands

**Frontend:**

```bash
cd apps/web
npm run dev         # Start development server
npm run build       # Production build
npm run type-check  # Type checking
npm run lint        # Linting
npm run format      # Formatting
```

**Backend:**

```bash
cd services/ai
python -m uvicorn app.main:app --reload  # Start development server
mypy .                                   # Type checking
pytest                                   # Run tests
```



### Environment configuration

All environment variables are now managed in a single `.env` file located in the project root (`bitcoin-academy/.env`).

Example `.env`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXTAUTH_SECRET=dev-secret-key
NEXTAUTH_URL=http://localhost:3000
NODE_ENV=development
DATABASE_URL=postgresql://user:password@localhost:5432/bitcoin_academy
SECRET_KEY=your-secret-key
API_PORT=8000
```




## API Documentation


### FastAPI Docs

Once the backend is running, you can access the interactive API documentation:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Main endpoints

- `GET /api/courses` - List all courses
- `GET /api/courses/{id}` - Get course details
- `GET /api/quizzes` - List quizzes
- `POST /api/progress` - Update progress
- `POST /api/chat` - Chat with AI tutor
- `GET /api/certificates` - List certificates



## Contributing

Contributions and feedback are welcome! To contribute:

1. Fork the repository
2. Create a branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -m 'Add new feature'`)
4. Push to your branch (`git push origin feature/new-feature`)
5. Open a Pull Request

### Guidelines

- Follow the project structure
- Use TypeScript for frontend, Python for backend
- Use clear variable and function names
- Comment complex logic
- Test before submitting PR
- Update documentation



## License

BitPolito Academy is open-source, released under the MIT license.
