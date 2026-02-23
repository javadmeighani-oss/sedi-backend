"""add_notification_prefs (V1 Notification Preferences)

Revision ID: 011_add_notification_prefs
Revises: 010_add_notification_guard_state
Create Date: 2025-02-23

V1: One row per user for notification preferences (channels, quiet hours, engagement).
Table: notification_prefs. FK user_id -> users.id ON DELETE CASCADE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_add_notification_prefs"
down_revision: Union[str, None] = "010_add_notification_guard_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_prefs",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("companion_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("health_alert_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reminder_medication_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reminder_appointment_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reminder_system_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quiet_start", sa.Text(), nullable=True),
        sa.Column("quiet_end", sa.Text(), nullable=True),
        sa.Column("engagement_level", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_prefs")
