"""quiz unification — course-scoped quizzes, concept tagging, attempt persistence

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Quiz gains a course-level scope (COURSE) alongside LESSON/CHAPTER_TEST,
    # for ad-hoc quizzes generated from the study page on an arbitrary topic.
    op.add_column("quiz", sa.Column("course_id", sa.String(), sa.ForeignKey("course.id"), nullable=True))
    op.add_column("quiz", sa.Column("created_at", sa.String(), nullable=True))

    # concept_tag / difficulty are the bridge to the agent-memory plan: they let
    # the quiz-adaptive selector and the episodic-memory distiller reason about
    # *what* a student got wrong, not just *that* they got something wrong.
    op.add_column("question", sa.Column("concept_tag", sa.String(), nullable=True))
    op.add_column("question", sa.Column("difficulty", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("question", "difficulty")
    op.drop_column("question", "concept_tag")
    op.drop_column("quiz", "created_at")
    op.drop_column("quiz", "course_id")
