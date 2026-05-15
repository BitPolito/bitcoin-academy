"""add answer_feedback table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-15

Adds answer_feedback table for student thumbs-up/down ratings (Q8).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "answer_feedback",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), server_default=sa.func.now()),
    )
    op.create_index("ix_answer_feedback_session_id", "answer_feedback", ["session_id"])
    op.create_index("ix_answer_feedback_course_id", "answer_feedback", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_answer_feedback_session_id", table_name="answer_feedback")
    op.drop_table("answer_feedback")
