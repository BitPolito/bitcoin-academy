"""Database initialisation at application startup (app.db.session.init_db).

The 0001 baseline migration builds the *current* models, so running every
revision on an empty database fails at 0002 (table already exists). These
tests run init_db against a throwaway SQLite file.
"""
import logging

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.models import Badge
from app.db.session import init_db


def _head_revision() -> str:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    head = ScriptDirectory.from_config(Config(str(ini))).get_current_head()
    assert head is not None
    return head


@pytest.fixture
def fresh_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    yield engine
    engine.dispose()


@pytest.mark.unit
def test_init_db_initialises_a_brand_new_database(fresh_engine):
    init_db(fresh_engine)

    tables = set(inspect(fresh_engine).get_table_names())
    assert {"course", "answer_feedback", "alembic_version"} <= tables
    with fresh_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        badges = conn.execute(text("SELECT count(*) FROM badge")).scalar()
    assert version == _head_revision()
    assert badges and badges > 0


@pytest.mark.unit
def test_init_db_is_idempotent(fresh_engine):
    init_db(fresh_engine)
    init_db(fresh_engine)

    with fresh_engine.connect() as conn:
        slugs = conn.execute(text(f"SELECT slug FROM {Badge.__tablename__}")).scalars().all()
    assert len(slugs) == len(set(slugs))


@pytest.mark.unit
def test_init_db_keeps_application_loggers_enabled(fresh_engine):
    """Alembic's fileConfig() disables existing loggers by default, which hid
    every app log line (including startup failures) after migrations ran."""
    app_logger = logging.getLogger("app.test_init_db_probe")

    init_db(fresh_engine)

    assert app_logger.disabled is False
