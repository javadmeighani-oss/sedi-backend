"""user_care_relationships (Gate 1 dependent users)

Revision ID: 017_user_care_relationships
Revises: 016_user_caregivers
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017_user_care_relationships"
down_revision: Union[str, None] = "016_user_caregivers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_care_relationships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("caregiver_user_id", sa.Integer(), nullable=False),
        sa.Column("dependent_user_id", sa.Integer(), nullable=False),
        sa.Column("relationship", sa.String(length=64), nullable=True),
        sa.Column("permissions_json", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["caregiver_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependent_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "caregiver_user_id",
            "dependent_user_id",
            name="uq_user_care_relationships_caregiver_dependent",
        ),
    )
    op.create_index("ix_user_care_relationships_caregiver", "user_care_relationships", ["caregiver_user_id"])
    op.create_index("ix_user_care_relationships_dependent", "user_care_relationships", ["dependent_user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_care_relationships_dependent", table_name="user_care_relationships")
    op.drop_index("ix_user_care_relationships_caregiver", table_name="user_care_relationships")
    op.drop_table("user_care_relationships")
