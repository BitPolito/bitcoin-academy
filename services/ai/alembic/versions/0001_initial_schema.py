"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-15

Baseline migration: creates all tables from the SQLAlchemy metadata using explicit DDL.
The schema is written out as it was at this revision, so later revisions can
apply on top of it. Tables that already exist (databases created by
create_all()) are skipped.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "app_user"):
        op.create_table(
            "app_user",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("email", sa.String(), unique=True, nullable=True),
            sa.Column("password_hash", sa.String(), nullable=True),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("role", sa.String(), server_default="student", nullable=False),
            sa.Column("created_at", sa.String(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table(bind, "section"):
        op.create_table(
            "section",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
        )

    if not _has_table(bind, "course"):
        op.create_table(
            "course",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("section_id", sa.String(), sa.ForeignKey("section.id"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        )

    if not _has_table(bind, "chapter"):
        op.create_table(
            "chapter",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("course_id", sa.String(), sa.ForeignKey("course.id"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        )

    if not _has_table(bind, "lesson"):
        op.create_table(
            "lesson",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("chapter_id", sa.String(), sa.ForeignKey("chapter.id"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        )

    if not _has_table(bind, "quiz"):
        op.create_table(
            "quiz",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("scope", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("passing_score", sa.Integer(), server_default="70", nullable=False),
            sa.Column("lesson_id", sa.String(), sa.ForeignKey("lesson.id"), nullable=True),
        )

    if not _has_table(bind, "chapter_test"):
        op.create_table(
            "chapter_test",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("chapter_id", sa.String(), sa.ForeignKey("chapter.id"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
        )

    if not _has_table(bind, "chapter_test_quiz"):
        op.create_table(
            "chapter_test_quiz",
            sa.Column("chapter_test_id", sa.String(), sa.ForeignKey("chapter_test.id"), primary_key=True),
            sa.Column("quiz_id", sa.String(), sa.ForeignKey("quiz.id"), primary_key=True),
            sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        )

    if not _has_table(bind, "question"):
        op.create_table(
            "question",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("quiz_id", sa.String(), sa.ForeignKey("quiz.id"), nullable=False),
            sa.Column("qtype", sa.String(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
            sa.Column("source_ref", sa.String(), nullable=True),
        )

    if not _has_table(bind, "option_choice"):
        op.create_table(
            "option_choice",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("question_id", sa.String(), sa.ForeignKey("question.id"), nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("is_correct", sa.Boolean(), server_default=sa.false(), nullable=False),
        )

    if not _has_table(bind, "quiz_attempt"):
        op.create_table(
            "quiz_attempt",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("quiz_id", sa.String(), sa.ForeignKey("quiz.id"), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=False),
            sa.Column("started_at", sa.String(), server_default=sa.func.now(), nullable=False),
            sa.Column("finished_at", sa.String(), nullable=True),
            sa.Column("score_pct", sa.Integer(), nullable=True),
            sa.Column("passed", sa.Boolean(), nullable=True),
        )

    if not _has_table(bind, "attempt_answer"):
        op.create_table(
            "attempt_answer",
            sa.Column("attempt_id", sa.String(), sa.ForeignKey("quiz_attempt.id"), primary_key=True),
            sa.Column("question_id", sa.String(), sa.ForeignKey("question.id"), primary_key=True),
            sa.Column("selected_id", sa.String(), sa.ForeignKey("option_choice.id"), nullable=True),
            sa.Column("free_text", sa.Text(), nullable=True),
            sa.Column("is_correct", sa.Boolean(), nullable=True),
        )

    if not _has_table(bind, "user_lesson_progress"):
        op.create_table(
            "user_lesson_progress",
            sa.Column("user_id", sa.String(), sa.ForeignKey("app_user.id"), primary_key=True),
            sa.Column("lesson_id", sa.String(), sa.ForeignKey("lesson.id"), primary_key=True),
            sa.Column("status", sa.String(), server_default="not_started", nullable=False),
            sa.Column("last_activity", sa.String(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_score", sa.Integer(), nullable=True),
        )

    if not _has_table(bind, "user_chapter_progress"):
        op.create_table(
            "user_chapter_progress",
            sa.Column("user_id", sa.String(), sa.ForeignKey("app_user.id"), primary_key=True),
            sa.Column("chapter_id", sa.String(), sa.ForeignKey("chapter.id"), primary_key=True),
            sa.Column("status", sa.String(), server_default="not_started", nullable=False),
            sa.Column("last_activity", sa.String(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table(bind, "user_course_progress"):
        op.create_table(
            "user_course_progress",
            sa.Column("user_id", sa.String(), sa.ForeignKey("app_user.id"), primary_key=True),
            sa.Column("course_id", sa.String(), sa.ForeignKey("course.id"), primary_key=True),
            sa.Column("percent", sa.Integer(), server_default="0", nullable=False),
            sa.Column("status", sa.String(), server_default="not_started", nullable=False),
            sa.Column("updated_at", sa.String(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table(bind, "course_document"):
        op.create_table(
            "course_document",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("course_id", sa.String(), sa.ForeignKey("course.id"), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("mime_type", sa.String(), nullable=True),
            sa.Column("size", sa.Integer(), server_default="0", nullable=False),
            sa.Column("status", sa.String(), server_default="uploading", nullable=False),
            sa.Column("processing_stage", sa.String(), server_default="queued", nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("document_type", sa.String(), server_default="lecture", nullable=False),
            sa.Column("parser_used", sa.String(), nullable=True),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("chunk_count", sa.Integer(), nullable=True),
            sa.Column("indexing_status", sa.String(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("extracted_text_preview", sa.Text(), nullable=True),
            sa.Column("sections_json", sa.Text(), nullable=True),
            sa.Column("sample_chunks_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.String(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table(bind, "chunk_parent"):
        op.create_table(
            "chunk_parent",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("doc_id", sa.String(), nullable=False),
            sa.Column("course_id", sa.String(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("citation_label", sa.String(), nullable=False),
            sa.Column("citation_page", sa.Integer(), nullable=False),
            sa.Column("citation_section", sa.String(), nullable=False),
        )

    if not _has_table(bind, "resource"):
        op.create_table(
            "resource",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("parent_type", sa.String(), nullable=False),
            sa.Column("parent_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("url", sa.String(), nullable=True),
            sa.Column("resource_type", sa.String(), server_default="other", nullable=False),
            sa.Column("mime_type", sa.String(), nullable=True),
            sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
            sa.Column("is_public", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_by", sa.String(), sa.ForeignKey("app_user.id"), nullable=True),
            sa.Column("created_at", sa.String(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table(bind, "badge"):
        op.create_table(
            "badge",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("slug", sa.String(), unique=True, nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("icon", sa.String(), server_default="🏅", nullable=False),
        )

    if not _has_table(bind, "user_badge"):
        op.create_table(
            "user_badge",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=False),
            sa.Column("badge_id", sa.String(), sa.ForeignKey("badge.id"), nullable=False),
            sa.Column("earned_at", sa.String(), server_default=sa.func.now(), nullable=False),
            sa.Column("context_id", sa.String(), nullable=True),
        )

    if not _has_table(bind, "certificate"):
        op.create_table(
            "certificate",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=False),
            sa.Column("course_id", sa.String(), sa.ForeignKey("course.id"), nullable=False),
            sa.Column("issued_at", sa.String(), server_default=sa.func.now(), nullable=False),
            sa.Column("code", sa.String(), unique=True, nullable=False),
            sa.Column("verification_hash", sa.String(), unique=True, nullable=False),
            sa.Column("grade_pct", sa.Integer(), nullable=True),
            sa.Column("hours", sa.Integer(), nullable=True),
            sa.Column("issuer_name", sa.String(), nullable=True),
            sa.Column("revoked", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("revoked_at", sa.String(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    # Downgrade drops everything created in the initial baseline
    bind = op.get_bind()
    for t in [
        "certificate", "user_badge", "badge", "resource", "chunk_parent", "course_document",
        "user_course_progress", "user_chapter_progress", "user_lesson_progress",
        "attempt_answer", "quiz_attempt", "option_choice", "question",
        "chapter_test_quiz", "chapter_test", "quiz", "lesson", "chapter",
        "course", "section", "app_user"
    ]:
        if _has_table(bind, t):
            op.drop_table(t)
