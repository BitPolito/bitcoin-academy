"""course builder — Chapter/Lesson status, source_refs, GenerationRun table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Chapter status (draft | published)
    op.add_column("chapter", sa.Column("status", sa.String(), nullable=True))
    op.execute("UPDATE chapter SET status = 'published' WHERE status IS NULL")

    # Lesson status + grounding anchor
    op.add_column("lesson", sa.Column("status", sa.String(), nullable=True))
    op.execute("UPDATE lesson SET status = 'published' WHERE status IS NULL")
    op.add_column("lesson", sa.Column("source_refs_json", sa.Text(), nullable=True))

    # Provenance table for outline / content generation jobs
    op.create_table(
        "generation_run",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("course_id", sa.String(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("doc_ids_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("started_at", sa.String(), nullable=True),
        sa.Column("finished_at", sa.String(), nullable=True),
        sa.Column("options_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("generation_run")
    op.drop_column("lesson", "source_refs_json")
    op.drop_column("lesson", "status")
    op.drop_column("chapter", "status")
