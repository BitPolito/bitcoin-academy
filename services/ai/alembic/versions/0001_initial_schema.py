"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-15

Baseline migration: creates all tables from the SQLAlchemy metadata.
Safe for both fresh databases and existing ones created by create_all()
(checkfirst=True makes every CREATE TABLE idempotent).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.db.models import Base  # noqa: PLC0415

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    from app.db.models import Base  # noqa: PLC0415

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
