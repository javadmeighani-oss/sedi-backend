"""user_caregivers contact registry (Gate 1)

Revision ID: 016_user_caregivers
Revises: 015_user_profile_facts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016_user_caregivers"
down_revision: Union[str, None] = "015_user_profile_facts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_caregivers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("relationship", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notify_daily_status", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notify_emergency", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_care_summary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_manage_profile", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("preferred_language", sa.String(length=16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_caregivers_owner_user_id", "user_caregivers", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_caregivers_owner_user_id", table_name="user_caregivers")
    op.drop_table("user_caregivers")
