"""Gate 4C — interaction_events timeline table

Revision ID: 037_gate4c_interaction_events
Revises: 036_gate3g_kb_fetch_review
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "037_gate4c_interaction_events"
down_revision: Union[str, None] = "036_gate3g_kb_fetch_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interaction_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "interaction_channel",
            sa.String(length=20),
            nullable=False,
            server_default="text",
        ),
        sa.Column("source_notification_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("conversation_id", sa.String(length=128), nullable=True),
        sa.Column("thread_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_notification_id"], ["notifications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interaction_events_user_id", "interaction_events", ["user_id"])
    op.create_index(
        "ix_interaction_events_source_notification_id",
        "interaction_events",
        ["source_notification_id"],
    )
    op.create_index("ix_interaction_events_created_at", "interaction_events", ["created_at"])
    op.create_index(
        "ix_interaction_events_conversation_id",
        "interaction_events",
        ["conversation_id"],
    )
    op.create_index("ix_interaction_events_thread_id", "interaction_events", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_interaction_events_thread_id", table_name="interaction_events")
    op.drop_index("ix_interaction_events_conversation_id", table_name="interaction_events")
    op.drop_index("ix_interaction_events_created_at", table_name="interaction_events")
    op.drop_index("ix_interaction_events_source_notification_id", table_name="interaction_events")
    op.drop_index("ix_interaction_events_user_id", table_name="interaction_events")
    op.drop_table("interaction_events")
