"""Section 10 — caregiver notification delivery intents

Revision ID: 046_section10_caregiver_notification_intents
Revises: 045_section10_caregiver_prefs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "046_section10_caregiver_notification_intents"
down_revision: Union[str, None] = "045_section10_caregiver_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "caregiver_notification_intents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("caregiver_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_type", sa.String(length=64), nullable=True),
        sa.Column("source_entity_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("payload_metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["caregiver_id"], ["user_caregivers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_caregiver_notification_intents_dedupe_key"),
    )
    op.create_index(
        "ix_caregiver_notification_intents_owner_user_id",
        "caregiver_notification_intents",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_caregiver_notification_intents_caregiver_id",
        "caregiver_notification_intents",
        ["caregiver_id"],
    )
    op.create_index(
        "ix_caregiver_notification_intents_status",
        "caregiver_notification_intents",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_caregiver_notification_intents_status", table_name="caregiver_notification_intents")
    op.drop_index("ix_caregiver_notification_intents_caregiver_id", table_name="caregiver_notification_intents")
    op.drop_index("ix_caregiver_notification_intents_owner_user_id", table_name="caregiver_notification_intents")
    op.drop_table("caregiver_notification_intents")
