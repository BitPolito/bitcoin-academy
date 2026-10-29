"""lesson content_hash for idempotent regeneration

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    cols = [c["name"] for c in inspector.get_columns("lesson")]
    if "content_hash" not in cols:
        op.add_column("lesson", sa.Column("content_hash", sa.String(), nullable=True))

def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    cols = [c["name"] for c in inspector.get_columns("lesson")]
    if "content_hash" in cols:
        op.drop_column("lesson", "content_hash")