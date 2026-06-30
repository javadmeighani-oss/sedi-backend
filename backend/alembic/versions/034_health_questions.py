"""health_questions (Gate 3 Q&A history)

Revision ID: 034_health_questions
Revises: 033_care_follow_up_tasks
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "034_health_questions"
down_revision: Union[str, None] = "033_care_follow_up_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("safety_level", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("citations_json", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="api"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_health_questions_user_created",
        "health_questions",
        ["user_id", "created_at"],
    )
    op.create_index("ix_health_questions_risk_level", "health_questions", ["risk_level"])


def downgrade() -> None:
    op.drop_index("ix_health_questions_risk_level", table_name="health_questions")
    op.drop_index("ix_health_questions_user_created", table_name="health_questions")
    op.drop_table("health_questions")
