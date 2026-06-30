"""user_care_plan_items (Gate 2 data-only care plan records)

Revision ID: 025_user_care_plan_items
Revises: 024_user_lifestyle_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "025_user_care_plan_items"
down_revision: Union[str, None] = "024_user_lifestyle_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_care_plan_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_care_plan_items_user_id", "user_care_plan_items", ["user_id"])
    op.create_index("ix_user_care_plan_items_status", "user_care_plan_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_user_care_plan_items_status", table_name="user_care_plan_items")
    op.drop_index("ix_user_care_plan_items_user_id", table_name="user_care_plan_items")
    op.drop_table("user_care_plan_items")
