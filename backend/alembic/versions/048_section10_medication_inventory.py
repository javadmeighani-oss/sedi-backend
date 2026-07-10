"""Section 10 — medication inventory fields

Revision ID: 048_section10_medication_inventory
Revises: 047_section10_emergency_escalation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "048_section10_medication_inventory"
down_revision: Union[str, None] = "047_section10_emergency_escalation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_medications", sa.Column("remaining_quantity", sa.Float(), nullable=True))
    op.add_column("user_medications", sa.Column("quantity_unit", sa.String(length=32), nullable=True))
    op.add_column("user_medications", sa.Column("refill_threshold", sa.Float(), nullable=True))
    op.add_column("user_medications", sa.Column("last_refill_at", sa.DateTime(), nullable=True))
    op.add_column("user_medications", sa.Column("estimated_end_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_medications", "estimated_end_at")
    op.drop_column("user_medications", "last_refill_at")
    op.drop_column("user_medications", "refill_threshold")
    op.drop_column("user_medications", "quantity_unit")
    op.drop_column("user_medications", "remaining_quantity")
