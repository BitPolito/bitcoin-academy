"""Shared pytest fixtures for unit and integration tests.

Uses an in-memory SQLite database so tests are fast, isolated, and require
no external services.

SQLite note: StaticPool forces all connections to reuse the same underlying
connection, which makes the in-memory database visible across threads (needed
because FastAPI runs endpoints in a thread pool).
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Badge,
    Base,
    Chapter,
    Course,
    Lesson,
    Section,
    User,
    UserRole,
)
from app.db.session import get_db
from app.main import app

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    _engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(_engine)
    yield _engine
    Base.metadata.drop_all(_engine)


@pytest.fixture(scope="function")
def db(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    _seed_badges(session)
    yield session
    session.close()


def _seed_badges(session: Session) -> None:
    for data in [
        {
            "id": "badge-lesson",
            "slug": "lesson_complete",
            "name": "Lesson Completed",
            "description": "First lesson done.",
            "icon": "📖",
        },
        {
            "id": "badge-course",
            "slug": "course_complete",
            "name": "Course Completed",
            "description": "All lessons done.",
            "icon": "🎓",
        },
    ]:
        if not session.query(Badge).filter_by(slug=data["slug"]).first():
            session.add(Badge(**data))
    session.commit()


# ---------------------------------------------------------------------------
# Helpers to build test entities
# ---------------------------------------------------------------------------

def make_user(db: Session, role: UserRole = UserRole.STUDENT) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=f"test-{uuid.uuid4()}@example.com",
        password_hash="hashed",
        display_name="Test User",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_course_with_lessons(db: Session, n_lessons: int = 2):
    """Create a Section → Course → Chapter → N Lessons tree. Returns (course, lessons)."""
    section = Section(id=str(uuid.uuid4()), title="Test Section")
    db.add(section)

    course = Course(
        id=str(uuid.uuid4()),
        section_id=section.id,
        title="Test Course",
    )
    db.add(course)

    chapter = Chapter(
        id=str(uuid.uuid4()),
        course_id=course.id,
        title="Test Chapter",
        order_index=0,
    )
    db.add(chapter)

    lessons = []
    for i in range(n_lessons):
        lesson = Lesson(
            id=str(uuid.uuid4()),
            chapter_id=chapter.id,
            title=f"Lesson {i + 1}",
            content="Content.",
            order_index=i,
        )
        db.add(lesson)
        lessons.append(lesson)

    db.commit()
    for obj in [section, course, chapter] + lessons:
        db.refresh(obj)
    return course, lessons


# ---------------------------------------------------------------------------
# TestClient fixture (overrides get_db with the in-memory session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def client(db: Session) -> TestClient:
    # The override creates a new Session from the same engine per request,
    # so each endpoint call gets a fresh session connected to the same in-memory DB.
    _engine = db.get_bind()
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

    def _override_get_db():
        session = _SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db, None)
