"""quiz unification — course-scoped quizzes, concept tagging, attempt persistence

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # Quiz gains a course-level scope (COURSE) alongside LESSON/CHAPTER_TEST,
    # for ad-hoc quizzes generated from the study page on an arbitrary topic.
    quiz_cols = [c["name"] for c in inspector.get_columns("quiz")]

    # Use batch_alter_table for SQLite compatibility when adding Foreign Keys
    with op.batch_alter_table("quiz", schema=None) as batch_op:
        if "course_id" not in quiz_cols:
            batch_op.add_column(
                sa.Column("course_id", sa.String(), sa.ForeignKey("course.id", name="fk_quiz_course_id"), nullable=True)
            )
        if "created_at" not in quiz_cols:
            batch_op.add_column(sa.Column("created_at", sa.String(), nullable=True))

    # concept_tag / difficulty are the bridge to the agent-memory plan: they let
    # the quiz-adaptive selector and the episodic-memory distiller reason about
    # *what* a student got wrong, not just *that* they got something wrong.
    question_cols = [c["name"] for c in inspector.get_columns("question")]
    with op.batch_alter_table("question", schema=None) as batch_op:
        if "concept_tag" not in question_cols:
            batch_op.add_column(sa.Column("concept_tag", sa.String(), nullable=True))
        if "difficulty" not in question_cols:
            batch_op.add_column(sa.Column("difficulty", sa.String(), nullable=True))

def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    question_cols = [c["name"] for c in inspector.get_columns("question")]
    with op.batch_alter_table("question", schema=None) as batch_op:
        if "difficulty" in question_cols:
            batch_op.drop_column("difficulty")
        if "concept_tag" in question_cols:
            batch_op.drop_column("concept_tag")

    quiz_cols = [c["name"] for c in inspector.get_columns("quiz")]
    with op.batch_alter_table("quiz", schema=None) as batch_op:
        if "created_at" in quiz_cols:
            batch_op.drop_column("created_at")
        if "course_id" in quiz_cols:
            batch_op.drop_column("course_id")
