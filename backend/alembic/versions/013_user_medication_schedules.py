"""user medication schedules and assignment fields (Phase V1.1B)

Revision ID: 013_user_medication_schedules
Revises: 012_add_addressing_preference
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013_user_medication_schedules"
down_revision: Union[str, None] = "012_add_addressing_preference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_medications", sa.Column("user_dosage", sa.String(length=128), nullable=True))
    op.add_column("user_medications", sa.Column("instructions", sa.Text(), nullable=True))
    op.add_column(
        "user_medications",
        sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("user_medications", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column(
        "user_medications",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "user_medication_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_medication_id", sa.Integer(), nullable=False),
        sa.Column("time_of_day", sa.Time(), nullable=False),
        sa.Column("days_of_week", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_medication_id"],
            ["user_medications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_medication_schedules_id"),
        "user_medication_schedules",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_medication_schedules_user_medication_id"),
        "user_medication_schedules",
        ["user_medication_id"],
        unique=False,
    )

    op.create_index(
        "uq_user_medications_user_medication",
        "user_medications",
        ["user_id", "medication_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_user_medications_user_medication", table_name="user_medications")
    op.drop_index(
        op.f("ix_user_medication_schedules_user_medication_id"),
        table_name="user_medication_schedules",
    )
    op.drop_index(op.f("ix_user_medication_schedules_id"), table_name="user_medication_schedules")
    op.drop_table("user_medication_schedules")
    op.drop_column("user_medications", "updated_at")
    op.drop_column("user_medications", "timezone")
    op.drop_column("user_medications", "reminder_enabled")
    op.drop_column("user_medications", "instructions")
    op.drop_column("user_medications", "user_dosage")
