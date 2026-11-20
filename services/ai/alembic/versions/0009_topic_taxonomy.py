"""cross-course topic taxonomy — foundational data layer (#139)

Adds the topic / topic_alias / topic_occurrence / topic_relation tables.
This layer is read-side only: retrieval and the evidence pack contract are
untouched by this migration (see docs/design/topic-taxonomy-isolation.md).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-20
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

    if "topic" not in existing_tables:
        op.create_table(
            "topic",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("canonical_name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("app_user.id"), nullable=True,
            ),
            sa.UniqueConstraint("canonical_name", name="uq_topic_canonical_name"),
        )

    if "topic_alias" not in existing_tables:
        op.create_table(
            "topic_alias",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "topic_id", sa.String(), sa.ForeignKey("topic.id"), nullable=False,
            ),
            sa.Column("alias", sa.String(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("app_user.id"), nullable=True,
            ),
            sa.UniqueConstraint("alias", name="uq_topic_alias_alias"),
        )
        op.create_index(
            "ix_topic_alias_topic_id", "topic_alias", ["topic_id"]
        )

    if "topic_occurrence" not in existing_tables:
        op.create_table(
            "topic_occurrence",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "topic_id", sa.String(), sa.ForeignKey("topic.id"), nullable=False,
            ),
            sa.Column(
                "course_id", sa.String(), sa.ForeignKey("course.id"), nullable=False,
            ),
            sa.Column(
                "lesson_id", sa.String(), sa.ForeignKey("lesson.id"), nullable=False,
            ),
            sa.Column("chunk_id", sa.String(), nullable=True),
            sa.Column("role", sa.String(), nullable=False, server_default="introduced"),
            sa.Column("matched_term", sa.String(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.UniqueConstraint(
                "topic_id", "lesson_id", "chunk_id",
                name="uq_topic_occurrence_topic_lesson_chunk",
            ),
        )
        op.create_index(
            "ix_topic_occurrence_topic_id", "topic_occurrence", ["topic_id"]
        )
        op.create_index(
            "ix_topic_occurrence_course_id", "topic_occurrence", ["course_id"]
        )
        op.create_index(
            "ix_topic_occurrence_lesson_id", "topic_occurrence", ["lesson_id"]
        )

    if "topic_relation" not in existing_tables:
        op.create_table(
            "topic_relation",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "topic_id", sa.String(), sa.ForeignKey("topic.id"), nullable=False,
            ),
            sa.Column(
                "related_topic_id", sa.String(), sa.ForeignKey("topic.id"),
                nullable=False,
            ),
            sa.Column("relation_type", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
            sa.Column(
                "course_id", sa.String(), sa.ForeignKey("course.id"), nullable=True,
            ),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("app_user.id"), nullable=True,
            ),
            sa.UniqueConstraint(
                "topic_id", "related_topic_id", "relation_type",
                name="uq_topic_relation_edge",
            ),
        )
        op.create_index(
            "ix_topic_relation_topic_id", "topic_relation", ["topic_id"]
        )
        op.create_index(
            "ix_topic_relation_related_topic_id",
            "topic_relation", ["related_topic_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    for table in ("topic_relation", "topic_occurrence", "topic_alias", "topic"):
        if table in existing_tables:
            op.drop_table(table)
