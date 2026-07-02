"""Gate 4-B — notification traceability fields (category, source, context_json, risk, template)

Revision ID: 039_gate4b_notification_context_fields
Revises: 038_gate4d3_notification_prefs_daily_time
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "039_gate4b_notification_context_fields"
down_revision: Union[str, None] = "038_gate4d3_notification_prefs_daily_time"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("category", sa.String(length=64), nullable=True))
    op.add_column("notifications", sa.Column("source_type", sa.String(length=64), nullable=True))
    op.add_column("notifications", sa.Column("source_id", sa.String(length=255), nullable=True))
    op.add_column("notifications", sa.Column("context_json", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("risk_level", sa.String(length=16), nullable=True))
    op.add_column("notifications", sa.Column("template_key", sa.String(length=100), nullable=True))

    op.create_index(
        "ix_notifications_user_category_created",
        "notifications",
        ["user_id", "category", "created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_notifications_source",
        "notifications",
        ["source_type", "source_id"],
        if_not_exists=True,
    )

    # Backfill category from legacy type (safe mapping only).
    op.execute(
        """
        UPDATE notifications
        SET category = CASE
            WHEN type = 'morning_brief' THEN 'daily_status'
            WHEN type IN ('connection_ping', 'companion_ping', 'engagement_nudge') THEN 'engagement_checkin'
            WHEN type = 'health_alert' THEN 'health_status'
            WHEN type = 'device_disconnected' THEN 'device_alert'
            ELSE 'system'
        END
        WHERE category IS NULL
        """
    )

    # Backfill risk_level from priority.
    op.execute(
        """
        UPDATE notifications
        SET risk_level = CASE
            WHEN priority = 'critical' THEN 'critical'
            WHEN priority = 'high' THEN 'high'
            WHEN priority = 'low' THEN 'low'
            ELSE 'normal'
        END
        WHERE risk_level IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_source", table_name="notifications", if_exists=True)
    op.drop_index("ix_notifications_user_category_created", table_name="notifications", if_exists=True)
    op.drop_column("notifications", "template_key")
    op.drop_column("notifications", "risk_level")
    op.drop_column("notifications", "context_json")
    op.drop_column("notifications", "source_id")
    op.drop_column("notifications", "source_type")
    op.drop_column("notifications", "category")
