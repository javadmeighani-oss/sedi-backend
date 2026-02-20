"""add_notification_guard_state (D2.0 Behavior Guard)

Revision ID: 010_add_notification_guard_state
Revises: 009_lock_notifications_dedupe_key
Create Date: 2025-02-20

D2.0: Cooldown guard state for health_alert notifications.
Table: notification_guard_state (user_id, channel, rule_id, last_sent_at, cooldown_until, updated_at).
Unique (user_id, channel, rule_id).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010_add_notification_guard_state"
down_revision: Union[str, None] = "009_lock_notifications_dedupe_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_guard_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "channel", "rule_id", name="uq_notification_guard_state_user_channel_rule"),
    )
    op.create_index(
        op.f("ix_notification_guard_state_user_id"),
        "notification_guard_state",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_guard_state_user_id"), table_name="notification_guard_state")
    op.drop_table("notification_guard_state")
