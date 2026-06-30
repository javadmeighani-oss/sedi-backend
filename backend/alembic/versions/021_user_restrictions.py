"""user_restrictions (Gate 2)

Revision ID: 021_user_restrictions
Revises: 020_user_goals
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021_user_restrictions"
down_revision: Union[str, None] = "020_user_goals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_restrictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("restriction_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_restrictions_user_id", "user_restrictions", ["user_id"])
    op.create_index("ix_user_restrictions_status", "user_restrictions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_user_restrictions_status", table_name="user_restrictions")
    op.drop_index("ix_user_restrictions_user_id", table_name="user_restrictions")
    op.drop_table("user_restrictions")
