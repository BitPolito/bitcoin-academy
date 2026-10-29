"""add course owner_id

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = [c["name"] for c in inspector.get_columns("course")]
    
    with op.batch_alter_table("course", schema=None) as batch_op:
        if "owner_id" not in columns:
            batch_op.add_column(
                sa.Column("owner_id", sa.String(), sa.ForeignKey("app_user.id", name="fk_course_owner_id"), nullable=True)
            )

def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = [c["name"] for c in inspector.get_columns("course")]
    
    with op.batch_alter_table("course", schema=None) as batch_op:
        if "owner_id" in columns:
            batch_op.drop_column("owner_id")