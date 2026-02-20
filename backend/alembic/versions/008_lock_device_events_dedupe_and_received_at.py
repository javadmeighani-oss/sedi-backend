"""lock_device_events_dedupe_and_received_at

Revision ID: 008_lock_dedupe_received_at
Revises: 007_user_behavior_profiles
Create Date: 2025-02-20

Lock device_events: UNIQUE index on dedupe_key, server default now() for received_at.
Idempotent-safe for Postgres (IF NOT EXISTS / IF EXISTS).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_lock_dedupe_received_at"
down_revision: Union[str, None] = "007_user_behavior_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create UNIQUE index on device_events(dedupe_key) if not exists (idempotent for Postgres)
    op.create_index(
        "ux_device_events_dedupe_key",
        "device_events",
        ["dedupe_key"],
        unique=True,
        if_not_exists=True,
    )
    # Set server default now() for received_at
    op.alter_column(
        "device_events",
        "received_at",
        existing_type=sa.DateTime(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Remove server default from received_at (set default to NULL)
    op.alter_column(
        "device_events",
        "received_at",
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )
    # Drop UNIQUE index if exists (idempotent for Postgres)
    op.drop_index(
        "ux_device_events_dedupe_key",
        table_name="device_events",
        if_exists=True,
    )
