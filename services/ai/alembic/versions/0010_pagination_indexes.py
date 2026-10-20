"""add indexes for cursor-paginated listings

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-03
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_course_active_id", "course", ["is_active", "id"])
    op.create_index(
        "ix_course_document_course_created_id",
        "course_document",
        ["course_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_course_document_course_created_id", table_name="course_document")
    op.drop_index("ix_course_active_id", table_name="course")
