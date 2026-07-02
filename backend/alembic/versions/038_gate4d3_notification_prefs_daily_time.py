"""Gate 4D-3 — notification_prefs.daily_notification_time

Revision ID: 038_gate4d3_notification_prefs_daily_time
Revises: 037_gate4c_interaction_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "038_gate4d3_notification_prefs_daily_time"
down_revision: Union[str, None] = "037_gate4c_interaction_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_prefs",
        sa.Column("daily_notification_time", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_prefs", "daily_notification_time")
