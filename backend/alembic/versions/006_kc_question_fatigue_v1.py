"""kc_question_fatigue_v1 (Question Fatigue Control V1)

Revision ID: 006_kc_question_fatigue_v1
Revises: 005_kc_candidates_metadata
Create Date: 2025-02-16

Question Fatigue Control V1: per-user daily cap, cooldown, burst guard, reject-streak.
Table: kc_question_policy_state (one row per user).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_kc_question_fatigue_v1"
down_revision: Union[str, None] = "005_kc_candidates_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kc_question_policy_state",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("asked_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_asked_at", sa.DateTime(), nullable=True),
        sa.Column("last_question_type", sa.Text(), nullable=True),
        sa.Column("consecutive_rejects", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_kc_question_policy_state_user_id"),
        "kc_question_policy_state",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_kc_question_policy_state_user_id"),
        table_name="kc_question_policy_state",
    )
    op.drop_table("kc_question_policy_state")
