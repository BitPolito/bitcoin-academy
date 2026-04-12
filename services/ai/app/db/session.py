"""Database session management."""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Badge, Base

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


_DEFAULT_BADGES = [
    {
        "slug": "lesson_complete",
        "name": "Lesson Completed",
        "description": "Awarded for completing your first lesson.",
        "icon": "📖",
    },
    {
        "slug": "course_complete",
        "name": "Course Completed",
        "description": "Awarded for completing an entire course.",
        "icon": "🎓",
    },
]


def _seed_badges(db: Session) -> None:
    for data in _DEFAULT_BADGES:
        if not db.query(Badge).filter_by(slug=data["slug"]).first():
            db.add(Badge(**data))
    db.commit()


def init_db() -> None:
    """Initialize the database by creating all tables and seeding static data."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_badges(db)
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session.

    Yields:
        A SQLAlchemy session that will be automatically closed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions outside of FastAPI dependencies.

    Yields:
        A SQLAlchemy session that will be automatically closed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
