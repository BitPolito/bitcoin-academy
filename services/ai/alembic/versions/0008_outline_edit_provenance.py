"""track manual outline edits

Revision ID: 0008
Revises: 0006
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "0008"
down_revision = "0006"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    chapter_cols = [c["name"] for c in inspector.get_columns("chapter")]
    if "is_human_modified" not in chapter_cols:
        op.add_column("chapter", sa.Column("is_human_modified", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "human_modified_at" not in chapter_cols:
        op.add_column("chapter", sa.Column("human_modified_at", sa.String(), nullable=True))
        
    lesson_cols = [c["name"] for c in inspector.get_columns("lesson")]
    if "is_human_modified" not in lesson_cols:
        op.add_column("lesson", sa.Column("is_human_modified", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "human_modified_at" not in lesson_cols:
        op.add_column("lesson", sa.Column("human_modified_at", sa.String(), nullable=True))

def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    lesson_cols = [c["name"] for c in inspector.get_columns("lesson")]
    if "human_modified_at" in lesson_cols:
        op.drop_column("lesson", "human_modified_at")
    if "is_human_modified" in lesson_cols:
        op.drop_column("lesson", "is_human_modified")
        
    chapter_cols = [c["name"] for c in inspector.get_columns("chapter")]
    if "human_modified_at" in chapter_cols:
        op.drop_column("chapter", "human_modified_at")
    if "is_human_modified" in chapter_cols:
        op.drop_column("chapter", "is_human_modified")