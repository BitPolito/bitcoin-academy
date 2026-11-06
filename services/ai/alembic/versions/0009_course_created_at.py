"""add course.created_at for cursor pagination

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    course_cols = [c["name"] for c in inspector.get_columns("course")]
    if "created_at" not in course_cols:
        op.add_column("course", sa.Column("created_at", sa.String(), nullable=True))
        # Existing rows have no recorded creation time. Backfill to a fixed
        # sentinel in the past rather than "now" for every row — with
        # created_at DESC ordering (newest first), this reliably sorts all
        # pre-existing courses after every newly created one, rather than
        # having them race "now" against courses created moments later.
        # The (created_at, id) composite cursor still makes ordering among
        # the backfilled rows themselves fully deterministic.
        op.execute(
            "UPDATE course SET created_at = '1970-01-01T00:00:00+00:00' "
            "WHERE created_at IS NULL"
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("course")}
    if "ix_course_created_at_id" not in existing_indexes:
        op.create_index(
            "ix_course_created_at_id", "course", ["created_at", "id"], unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("course")}
    if "ix_course_created_at_id" in existing_indexes:
        op.drop_index("ix_course_created_at_id", table_name="course")

    course_cols = [c["name"] for c in inspector.get_columns("course")]
    if "created_at" in course_cols:
        op.drop_column("course", "created_at")
