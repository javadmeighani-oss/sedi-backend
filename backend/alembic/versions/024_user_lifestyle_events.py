"""user_lifestyle_events (Gate 2 daily lifestyle logs)

Revision ID: 024_user_lifestyle_events
Revises: 023_user_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "024_user_lifestyle_events"
down_revision: Union[str, None] = "023_user_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_lifestyle_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_lifestyle_events_user_id", "user_lifestyle_events", ["user_id"])
    op.create_index("ix_user_lifestyle_events_occurred_at", "user_lifestyle_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_user_lifestyle_events_occurred_at", table_name="user_lifestyle_events")
    op.drop_index("ix_user_lifestyle_events_user_id", table_name="user_lifestyle_events")
    op.drop_table("user_lifestyle_events")
