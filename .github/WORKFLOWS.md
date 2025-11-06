# CI/CD Workflows

## Overview

BitPolito Academy uses GitHub Actions for continuous integration and continuous deployment. Workflows are automatically triggered on push/pull requests and run on schedule. The CI/CD pipeline is comprehensive, production-ready, and follows GitHub Actions best practices.

## Quick Summary

| Workflow | Trigger | Tests |
|----------|---------|-------|
| **Frontend** | Push/PR to master/develop | Node.js 18.x, 20.x (ESLint, Prettier, TypeScript, Jest) + Codecov |
| **Backend** | Push/PR to master/develop | Python 3.10, 3.11, 3.12 (Flake8, MyPy, Pytest) + Codecov |
| **Full Suite** | Push/PR, Daily 2 AM UTC | Code quality + Security audits |

## Workflows

### 1. Frontend Workflow (`.github/workflows/frontend.yml`)

**Trigger events:**
- Push to `master` or `develop`
- Pull requests to `master` or `develop`
- Changes to `apps/web/**` or workflow file

**Jobs:**
- **test**: Run linting, type checking, and unit tests
  - Node.js versions: 18.x, 20.x
  - Steps:
    - Install dependencies
    - ESLint
    - Prettier format check
    - TypeScript type check
    - Jest unit tests
    - Upload coverage to Codecov

- **build**: Build Next.js application
  - Requires `test` job to pass
  - Uploads build artifacts

### 2. Backend Workflow (`.github/workflows/backend.yml`)

**Trigger events:**
- Push to `master` or `develop`
- Pull requests to `master` or `develop`
- Changes to `services/ai/**` or workflow file

**Jobs:**
- **test**: Run linting, type checking, and tests
  - Python versions: 3.10, 3.11, 3.12
  - Steps:
    - Install dependencies
    - Flake8 linting
    - MyPy type checking
    - Pytest unit tests
    - Pytest integration tests
    - Upload coverage to Codecov

- **build**: Verify installation and artifact preparation
  - Requires `test` job to pass
  - Python 3.11
  - Uploads build artifacts

### 3. Full Test Suite (`.github/workflows/tests.yml`)

**Trigger events:**
- Push to `master` or `develop`
- Pull requests to `master` or `develop`
- Schedule: Daily at 2 AM UTC

**Jobs:**
- Runs frontend and backend workflows in parallel
- Includes code quality checks
- Runs security checks (npm audit, pip-audit)

## Workflow Status

You can check workflow status in the GitHub UI:

1. Go to repository
2. Click on "Actions" tab
3. Select workflow from list

## Badges

You can add workflow badges to README:

```markdown
![Frontend Tests](https://github.com/BitPolito/bitcoin-academy/workflows/Frontend%20Tests%20&%20Build/badge.svg)
![Backend Tests](https://github.com/BitPolito/bitcoin-academy/workflows/Backend%20Tests%20&%20Build/badge.svg)
```

## Configuration Files

### Frontend Configuration
- `.eslintrc.json` - ESLint configuration
- `.prettierrc.json` - Prettier configuration
- `jest.config.js` - Jest test configuration
- `jest.setup.js` - Jest test setup

### Backend Configuration
- `pyproject.toml` - Project metadata and tool configs
- `pytest.ini` - Pytest configuration
- `mypy.ini` - MyPy type checking configuration

## Local Development

Before pushing, run tests locally:

```bash
# Frontend
npm run test:web

# Backend
npm run test:api

# All tests
npm run test

# Linting and formatting
npm run lint
npm run format
```

## Troubleshooting

### Workflow not triggering

1. Check workflow file syntax in `.github/workflows/`
2. Verify branch protection rules
3. Check push permissions

### Tests failing in CI but passing locally

1. Check Node.js/Python version differences
2. Verify environment variables
3. Check for timing-dependent tests
4. Review log artifacts

### Coverage not uploading

1. Verify Codecov integration
2. Check coverage report format
3. Review Codecov configuration

## Security Considerations

- Secrets are managed through GitHub Actions secrets
- No credentials should be committed
- Regular dependency audits via `npm audit` and `pip-audit`

## Performance

Workflow optimization tips:

1. Use `cache` action for dependencies
2. Run jobs in parallel when possible
3. Use matrix strategy for multiple versions
4. Only run affected workflows on path changes

## Next Steps

Future enhancements:

- [ ] Add deployment workflows
- [ ] Add performance testing
- [ ] Add e2e testing
- [ ] Add Docker image building and pushing
- [ ] Add code coverage badges

---