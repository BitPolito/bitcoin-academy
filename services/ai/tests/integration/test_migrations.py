import os
import pytest
from sqlalchemy import create_engine, inspect
from alembic.config import Config
from alembic import command

@pytest.mark.integration
def test_alembic_upgrade_head_on_empty_db(tmp_path, monkeypatch):
    """
    Issue #207: Ensure 'alembic upgrade head' successfully runs from 0001 to head
    on a completely empty database without duplicate table/column OperationalErrors.
    """
    # 1. Setup a fresh, empty SQLite database in a temporary directory
    db_path = tmp_path / "test_migrations.db"
    db_url = f"sqlite:///{db_path}"

    # 2. Mock the app's settings so alembic's env.py targets our empty test DB
    from app.core.config import settings
    if hasattr(settings, "SQLALCHEMY_DATABASE_URI"):
        monkeypatch.setattr(settings, "SQLALCHEMY_DATABASE_URI", db_url)
    if hasattr(settings, "DATABASE_URL"):
        monkeypatch.setattr(settings, "DATABASE_URL", db_url)

    # Also set env variables just in case
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", db_url)

    # Configure Alembic dynamically
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 3. Execute upgrade head
    # This will crash if 0001 uses Base.metadata.create_all()
    # and 0002 tries to create answer_feedback again.
    command.upgrade(alembic_cfg, "head")

    # 4. Verify the schema reached head successfully
    engine = create_engine(db_url)
    inspector = inspect(engine)

    # Assert Baseline (0001)
    assert inspector.has_table("app_user")
    assert inspector.has_table("course")
    assert inspector.has_table("chunk_parent")

    # Assert 0002
    assert inspector.has_table("answer_feedback")

    # Assert 0004
    assert inspector.has_table("generation_run")

    # Assert 0004, 0005, 0008 columns applied to lesson
    lesson_cols = [c["name"] for c in inspector.get_columns("lesson")]
    assert "status" in lesson_cols                # 0004
    assert "source_refs_json" in lesson_cols      # 0004
    assert "content_hash" in lesson_cols          # 0005
    assert "is_human_modified" in lesson_cols     # 0008

    # Assert 0006 columns applied to quiz
    quiz_cols = [c["name"] for c in inspector.get_columns("quiz")]
    assert "course_id" in quiz_cols               # 0006

    # 5. Verify downgrade is clean (Rolls back to base)
    command.downgrade(alembic_cfg, "base")
    inspector = inspect(engine)
    assert not inspector.has_table("app_user")
    assert not inspector.has_table("answer_feedback")

def _describe_schema(url: str) -> dict:
    inspector = inspect(create_engine(url))
    schema = {}
    for table in inspector.get_table_names():
        if table == "alembic_version":
            continue
        schema[table] = {
            "columns": sorted(c["name"] for c in inspector.get_columns(table)),
            "indexes": sorted(
                (tuple(i["column_names"]), bool(i["unique"])) for i in inspector.get_indexes(table)
            ),
            "foreign_keys": sorted(
                (tuple(fk["constrained_columns"]), fk["referred_table"])
                for fk in inspector.get_foreign_keys(table)
            ),
        }
    return schema


@pytest.mark.integration
def test_alembic_head_matches_models(tmp_path, monkeypatch):
    """`alembic upgrade head` builds the same tables, columns, indexes and
    foreign keys as Base.metadata.create_all(), the path init_db() takes."""
    from app.core.config import settings
    from app.db.models import Base

    migrated_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    created_url = f"sqlite:///{tmp_path / 'created.db'}"
    monkeypatch.setattr(settings, "DATABASE_URL", migrated_url)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", migrated_url)
    command.upgrade(alembic_cfg, "head")
    Base.metadata.create_all(create_engine(created_url))

    assert _describe_schema(migrated_url) == _describe_schema(created_url)
