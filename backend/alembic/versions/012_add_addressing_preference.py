"""add addressing_preference to user_profile_core (Phase V1.1A)

Revision ID: 012_add_addressing_preference
Revises: 011_add_notification_prefs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012_add_addressing_preference"
down_revision: Union[str, None] = "011_add_notification_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profile_core",
        sa.Column("addressing_preference", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profile_core", "addressing_preference")
