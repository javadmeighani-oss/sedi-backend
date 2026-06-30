"""user_goals (Gate 2)

Revision ID: 020_user_goals
Revises: 019_user_habits
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020_user_goals"
down_revision: Union[str, None] = "019_user_habits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_goals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="lifestyle"),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("priority", sa.String(length=16), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_goals_user_id", "user_goals", ["user_id"])
    op.create_index("ix_user_goals_status", "user_goals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_user_goals_status", table_name="user_goals")
    op.drop_index("ix_user_goals_user_id", table_name="user_goals")
    op.drop_table("user_goals")
