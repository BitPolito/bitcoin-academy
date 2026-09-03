"""track manual outline edits

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chapter",
        sa.Column("is_human_modified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("chapter", sa.Column("human_modified_at", sa.String(), nullable=True))
    op.add_column(
        "lesson",
        sa.Column("is_human_modified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("lesson", sa.Column("human_modified_at", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("lesson", "human_modified_at")
    op.drop_column("lesson", "is_human_modified")
    op.drop_column("chapter", "human_modified_at")
    op.drop_column("chapter", "is_human_modified")
