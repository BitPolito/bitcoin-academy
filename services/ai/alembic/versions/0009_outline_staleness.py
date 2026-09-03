"""track outline staleness and source snapshots

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("course", sa.Column("outline_stale", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("course", sa.Column("outline_stale_reason", sa.Text(), nullable=True))
    op.add_column("course", sa.Column("outline_stale_at", sa.String(), nullable=True))
    for table in ("chapter", "lesson"):
        op.add_column(table, sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.add_column(table, sa.Column("stale_reason", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("stale_at", sa.String(), nullable=True))
    op.add_column("lesson", sa.Column("source_snapshot_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lesson", "source_snapshot_json")
    for table in ("lesson", "chapter"):
        op.drop_column(table, "stale_at")
        op.drop_column(table, "stale_reason")
        op.drop_column(table, "is_stale")
    op.drop_column("course", "outline_stale_at")
    op.drop_column("course", "outline_stale_reason")
    op.drop_column("course", "outline_stale")
