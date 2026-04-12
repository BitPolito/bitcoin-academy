---
name: Progress & Badge system implementation
description: Details and gotchas from the progress tracking + badge system feature
type: project
---

Progress and badge system fully implemented (2026-04-13).

**Why:** Scope required course/lesson progress tracking and a gamification badge system.

**How to apply:** When touching progress or badge code, be aware of these decisions:
- `StaticPool` is required in conftest.py for SQLite in-memory tests because FastAPI runs endpoints in a threadpool (SQLite objects can't cross threads otherwise).
- Starlette was upgraded from 0.27.0 to 1.0.0 (system-level) for httpx 0.28.1 compatibility. The environment has PYTHONPATH pointing to system site-packages which takes priority over the venv.
- `test_auth_api.py` and `test_health.py` were already broken.
- badge seeding (`lesson_complete`, `course_complete`) happens in `session.py:init_db()` and in `conftest.py:_seed_badges()` for tests.
