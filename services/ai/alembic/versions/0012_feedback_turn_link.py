"""link answer_feedback to the persisted study_turn (issue #136)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = {c["name"] for c in inspector.get_columns("answer_feedback")}

    if "turn_id" not in columns:
        # Nullable: feedback predates persisted sessions, and a client that never
        # sends session_id with its study request still has no turn to link to.
        # ON DELETE SET NULL rather than CASCADE — deleting a study session must
        # not silently destroy the feedback signal recorded against its answers.
        with op.batch_alter_table("answer_feedback") as batch_op:
            batch_op.add_column(sa.Column("turn_id", sa.String(), nullable=True))
            batch_op.create_foreign_key(
                "fk_answer_feedback_turn_id",
                "study_turn",
                ["turn_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            "ix_answer_feedback_turn_id", "answer_feedback", ["turn_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = {c["name"] for c in inspector.get_columns("answer_feedback")}

    if "turn_id" in columns:
        op.drop_index("ix_answer_feedback_turn_id", table_name="answer_feedback")
        with op.batch_alter_table("answer_feedback") as batch_op:
            batch_op.drop_constraint("fk_answer_feedback_turn_id", type_="foreignkey")
            batch_op.drop_column("turn_id")
