"""health_symptom_reports (Gate 3 structured symptom log)

Revision ID: 035_health_symptom_reports
Revises: 034_health_questions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "035_health_symptom_reports"
down_revision: Union[str, None] = "034_health_questions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_symptom_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.Column("symptom_label", sa.String(length=256), nullable=False),
        sa.Column("symptom_code", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("body_area", sa.String(length=64), nullable=True),
        sa.Column("duration", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("linked_question_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_question_id"], ["health_questions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_health_symptom_reports_user_reported",
        "health_symptom_reports",
        ["user_id", "reported_at"],
    )
    op.create_index(
        "ix_health_symptom_reports_user_status",
        "health_symptom_reports",
        ["user_id", "status"],
    )
    op.create_index("ix_health_symptom_reports_severity", "health_symptom_reports", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_health_symptom_reports_severity", table_name="health_symptom_reports")
    op.drop_index("ix_health_symptom_reports_user_status", table_name="health_symptom_reports")
    op.drop_index("ix_health_symptom_reports_user_reported", table_name="health_symptom_reports")
    op.drop_table("health_symptom_reports")
