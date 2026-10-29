"""add course_document.section_tree_json

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = [c["name"] for c in inspector.get_columns("course_document")]
    if "section_tree_json" not in columns:
        op.add_column("course_document", sa.Column("section_tree_json", sa.Text(), nullable=True))

def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = [c["name"] for c in inspector.get_columns("course_document")]
    if "section_tree_json" in columns:
        op.drop_column("course_document", "section_tree_json")