"""gate1 identity profile extensions

Revision ID: 014_gate1_identity_profile_extensions
Revises: 013_user_medication_schedules
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_gate1_identity_profile_extensions"
down_revision: Union[str, None] = "013_user_medication_schedules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("account_type", sa.String(length=16), nullable=False, server_default="normal"),
    )
    op.add_column("user_profile_core", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("user_profile_core", sa.Column("timezone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profile_core", "timezone")
    op.drop_column("user_profile_core", "date_of_birth")
    op.drop_column("users", "account_type")
