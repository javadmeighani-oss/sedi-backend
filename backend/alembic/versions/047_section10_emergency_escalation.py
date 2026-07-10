"""Section 10 — emergency escalation and voice-call request foundations

Revision ID: 047_section10_emergency_escalation
Revises: 046_section10_caregiver_notification_intents
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "047_section10_emergency_escalation"
down_revision: Union[str, None] = "046_section10_caregiver_notification_intents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emergency_escalation_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("reason_category", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("current_state", sa.String(length=64), nullable=False, server_default="monitoring"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_user_interaction_at", sa.DateTime(), nullable=True),
        sa.Column("last_notification_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_source", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_emergency_escalation_records_owner_user_id",
        "emergency_escalation_records",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_emergency_escalation_records_current_state",
        "emergency_escalation_records",
        ["current_state"],
    )

    op.create_table(
        "voice_call_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("caregiver_id", sa.Integer(), nullable=False),
        sa.Column("escalation_id", sa.Integer(), nullable=True),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="fa"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_reference", sa.String(length=128), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["caregiver_id"], ["user_caregivers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escalation_id"], ["emergency_escalation_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voice_call_requests_owner_user_id", "voice_call_requests", ["owner_user_id"])
    op.create_index("ix_voice_call_requests_status", "voice_call_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_voice_call_requests_status", table_name="voice_call_requests")
    op.drop_index("ix_voice_call_requests_owner_user_id", table_name="voice_call_requests")
    op.drop_table("voice_call_requests")
    op.drop_index("ix_emergency_escalation_records_current_state", table_name="emergency_escalation_records")
    op.drop_index("ix_emergency_escalation_records_owner_user_id", table_name="emergency_escalation_records")
    op.drop_table("emergency_escalation_records")
