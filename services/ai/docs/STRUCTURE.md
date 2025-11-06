# Backend Directory Structure

## Overview

```
services/ai/
├── config/                 # Configuration files
│   ├── pytest.ini         # Pytest configuration
│   ├── mypy.ini           # MyPy type checking config
│   ├── setup.cfg          # Flake8 & setuptools config
│   └── README.md          # Configuration documentation
│
├── docs/                  # Documentation
│   └── (add API docs, architecture docs here)
│
├── app/                   # Application source code
│   ├── __init__.py
│   ├── main.py           # FastAPI app entry point
│   ├── api_deps.py
│   ├── api/              # API routes
│   ├── core/             # Core configuration & errors
│   ├── db/               # Database models & sessions
│   ├── middleware/       # Custom middleware
│   ├── rag/              # RAG (Retrieval-Augmented Generation)
│   ├── repositories/     # Data access layer
│   ├── schemas/          # Pydantic schemas
│   └── services/         # Business logic
│
├── tests/                # Test suite
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests
│
├── pyproject.toml       # Project metadata & dependencies
├── README.md           # Backend documentation
├── requirements.txt    # Dependencies (legacy)
├── py.typed           # PEP 561 type hints marker
├── package.json       # Node.js dev tools
├── .env.example       # Environment template
├── .dockerignore      # Docker ignore patterns
└── Dockerfile         # (Optional) Docker image
```

## Key Files

### Configuration Files (in `config/`)
- **pytest.ini** - Test runner configuration with markers
- **mypy.ini** - Static type checking rules
- **setup.cfg** - Flake8 linting rules and coverage config

### Project Metadata
- **pyproject.toml** - Main project configuration
  - Package metadata
  - Dependencies and optional dev dependencies
  - Tool configurations (black, isort, pylint)
  - Pytest configuration override

- **requirements.txt** - Legacy dependency list (generated from pyproject.toml)
  - Use `pip install -e .[dev]` instead

### Documentation
- **README.md** - Backend setup and usage documentation
- **docs/** - Detailed documentation (API specs, guides, etc.)

### Source Code
- **app/** - All application code, organized by domain

### Tests
- **tests/** - Test files organized by type
  - unit/ - Unit tests (fast, isolated)
  - integration/ - Integration tests (slower, with dependencies)

## Why This Structure?

1. **config/** - Keeps configuration files organized and separate from code
2. **docs/** - Dedicated space for documentation
3. **Configuration in pyproject.toml** - Single source of truth for project metadata
4. **Separation of concerns** - Code, tests, config, and docs clearly separated

## Installation & Usage

```bash
# Install with dev dependencies
pip install -e .[dev]

# Run tests (uses config/pytest.ini)
pytest

# Type check (uses config/mypy.ini)
mypy app

# Lint (uses config/setup.cfg)
flake8 app
```

## Adding Documentation

Place documentation in the `docs/` folder:
- `API.md` - API endpoint documentation
- `ARCHITECTURE.md` - System architecture
- `DEPLOYMENT.md` - Deployment guide
- `DEVELOPMENT.md` - Development guide
