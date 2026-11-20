"""add course.outline_hash for rung-0 exact-match caching (issue #137/#161)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = {c["name"] for c in inspector.get_columns("course")}

    if "outline_hash" not in columns:
        op.add_column("course", sa.Column("outline_hash", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = {c["name"] for c in inspector.get_columns("course")}

    if "outline_hash" in columns:
        with op.batch_alter_table("course") as batch_op:
            batch_op.drop_column("outline_hash")
