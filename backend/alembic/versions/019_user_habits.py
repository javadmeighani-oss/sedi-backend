"""user_habits (Gate 2)

Revision ID: 019_user_habits
Revises: 018_device_subject_user
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019_user_habits"
down_revision: Union[str, None] = "018_device_subject_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_habits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("frequency", sa.String(length=64), nullable=True),
        sa.Column("target_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_habits_user_id", "user_habits", ["user_id"])
    op.create_index("ix_user_habits_status", "user_habits", ["status"])


def downgrade() -> None:
    op.drop_index("ix_user_habits_status", table_name="user_habits")
    op.drop_index("ix_user_habits_user_id", table_name="user_habits")
    op.drop_table("user_habits")
