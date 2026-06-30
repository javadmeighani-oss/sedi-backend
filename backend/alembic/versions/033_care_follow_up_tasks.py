"""care_follow_up_tasks (Gate 3 follow-up tasks)

Revision ID: 033_care_follow_up_tasks
Revises: 032_care_recommendations
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "033_care_follow_up_tasks"
down_revision: Union[str, None] = "032_care_recommendations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "care_follow_up_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("linked_recommendation_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_recommendation_id"], ["care_recommendations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_care_follow_up_tasks_user_status_due",
        "care_follow_up_tasks",
        ["user_id", "status", "due_at"],
    )
    op.create_index(
        "ix_care_follow_up_tasks_user_created",
        "care_follow_up_tasks",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_care_follow_up_tasks_user_created", table_name="care_follow_up_tasks")
    op.drop_index("ix_care_follow_up_tasks_user_status_due", table_name="care_follow_up_tasks")
    op.drop_table("care_follow_up_tasks")
