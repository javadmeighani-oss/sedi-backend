"""care_risk_assessments (Gate 3 safety audit)

Revision ID: 031_care_risk_assessments
Revises: 030_knowledge_ingestion_runs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "031_care_risk_assessments"
down_revision: Union[str, None] = "030_knowledge_ingestion_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "care_risk_assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=True),
        sa.Column("message_hash", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="api"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_care_risk_assessments_user_created",
        "care_risk_assessments",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_care_risk_assessments_risk_created",
        "care_risk_assessments",
        ["risk_level", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_care_risk_assessments_risk_created", table_name="care_risk_assessments")
    op.drop_index("ix_care_risk_assessments_user_created", table_name="care_risk_assessments")
    op.drop_table("care_risk_assessments")
