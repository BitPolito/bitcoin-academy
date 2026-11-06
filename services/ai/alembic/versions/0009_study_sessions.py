"""add study_session and study_turn tables

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
    existing_tables = inspector.get_table_names()

    if "study_session" not in existing_tables:
        op.create_table(
            "study_session",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=False),
            sa.Column("course_id", sa.String(), sa.ForeignKey("course.id"), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("started_at", sa.String(), nullable=False),
            sa.Column("last_active_at", sa.String(), nullable=False),
        )
    if "study_turn" not in existing_tables:
        op.create_table(
            "study_turn",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "session_id",
                sa.String(),
                sa.ForeignKey("study_session.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("citations_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("model_tier", sa.String(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "study_turn" in existing_tables:
        op.drop_table("study_turn")
    if "study_session" in existing_tables:
        op.drop_table("study_session")
