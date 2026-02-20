"""lock_notifications_dedupe_key_unique

Revision ID: 009_lock_notifications_dedupe_key
Revises: 008_lock_dedupe_received_at
Create Date: 2025-02-20

UNIQUE index on notifications(dedupe_key). Postgres-safe, idempotent.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "009_lock_notifications_dedupe_key"
down_revision: Union[str, None] = "008_lock_dedupe_received_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ux_notifications_dedupe_key",
        "notifications",
        ["dedupe_key"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_notifications_dedupe_key",
        table_name="notifications",
        if_exists=True,
    )
