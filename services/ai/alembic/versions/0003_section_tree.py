"""add course_document.section_tree_json

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

Nested heading tree (title, level, page span, parent-chunk anchors) extracted
at ingest — structure source for course builder outline generation (Fase 1).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_document", sa.Column("section_tree_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("course_document", "section_tree_json")
