"""user_behavior_profiles (Behavior Layer V1)

Revision ID: 007_user_behavior_profiles
Revises: 006_kc_question_fatigue_v1
Create Date: 2025-02-17

Behavior Layer V1: per-user behavior profile (score, mode, daily counts, last initiated/interaction).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_user_behavior_profiles"
down_revision: Union[str, None] = "006_kc_question_fatigue_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_behavior_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("mode", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("daily_initiated_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_initiated_at", sa.DateTime(), nullable=True),
        sa.Column("last_interaction_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_user_behavior_profiles_user_id"),
        "user_behavior_profiles",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_behavior_profiles_user_id"),
        table_name="user_behavior_profiles",
    )
    op.drop_table("user_behavior_profiles")
