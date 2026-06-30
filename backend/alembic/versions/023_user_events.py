"""user_events (Gate 2 unified calendar/deadlines/appointments)

Revision ID: 023_user_events
Revises: 022_user_doctors
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023_user_events"
down_revision: Union[str, None] = "022_user_doctors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_domain", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("event_type", sa.String(length=64), nullable=False, server_default="other"),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("location", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("importance", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reminder_offsets_json", sa.Text(), nullable=True),
        sa.Column("recurrence_rule", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["user_doctors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_events_user_id", "user_events", ["user_id"])
    op.create_index("ix_user_events_status", "user_events", ["status"])
    op.create_index("ix_user_events_event_domain", "user_events", ["event_domain"])
    op.create_index("ix_user_events_event_type", "user_events", ["event_type"])
    op.create_index("ix_user_events_starts_at", "user_events", ["starts_at"])


def downgrade() -> None:
    op.drop_index("ix_user_events_starts_at", table_name="user_events")
    op.drop_index("ix_user_events_event_type", table_name="user_events")
    op.drop_index("ix_user_events_event_domain", table_name="user_events")
    op.drop_index("ix_user_events_status", table_name="user_events")
    op.drop_index("ix_user_events_user_id", table_name="user_events")
    op.drop_table("user_events")
