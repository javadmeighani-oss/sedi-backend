"""Gate 2 V1 — birth calendar fields on user_profile_core

Revision ID: 044_gate2_birth_calendar_fields
Revises: 043_gate5e_ml_shadow_foundation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "044_gate2_birth_calendar_fields"
down_revision: Union[str, None] = "043_gate5e_ml_shadow_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profile_core", sa.Column("birth_day", sa.Integer(), nullable=True))
    op.add_column("user_profile_core", sa.Column("birth_month", sa.Integer(), nullable=True))
    op.add_column(
        "user_profile_core",
        sa.Column("calendar_type", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profile_core", "calendar_type")
    op.drop_column("user_profile_core", "birth_month")
    op.drop_column("user_profile_core", "birth_day")
