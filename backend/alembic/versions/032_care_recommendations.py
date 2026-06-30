"""care_recommendations (Gate 3 derived care guidance)

Revision ID: 032_care_recommendations
Revises: 031_care_risk_assessments
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "032_care_recommendations"
down_revision: Union[str, None] = "031_care_risk_assessments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "care_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("safety_level", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source_refs_json", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="system"),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_care_recommendations_user_status_created",
        "care_recommendations",
        ["user_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_care_recommendations_user_status_created", table_name="care_recommendations")
    op.drop_table("care_recommendations")
