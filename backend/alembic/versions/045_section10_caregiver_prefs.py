"""Section 10 — caregiver vital-alert preference and emergency priority

Revision ID: 045_section10_caregiver_prefs
Revises: 044_gate2_birth_calendar_fields
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "045_section10_caregiver_prefs"
down_revision: Union[str, None] = "044_gate2_birth_calendar_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_caregivers",
        sa.Column(
            "notify_vital_alerts",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "user_caregivers",
        sa.Column("emergency_priority", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_caregivers", "emergency_priority")
    op.drop_column("user_caregivers", "notify_vital_alerts")
