"""A4 inbox visibility: additive hide-from-inbox column (no hard delete).

Revision ID: 087_a4_notification_inbox_visibility
Revises: 086_i9_vital_observation_context_authority

SCHEMA ONLY. Nullable inbox_hidden_at; existing rows remain NULL.
User hide is projection-only — never deletes Notification rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "087_a4_notification_inbox_visibility"
down_revision: Union[str, None] = "086_i9_vital_observation_context_authority"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("inbox_hidden_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notifications", "inbox_hidden_at")
