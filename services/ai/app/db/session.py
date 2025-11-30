"""Database session management."""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)


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
