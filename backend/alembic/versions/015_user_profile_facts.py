"""user_profile_facts (Gate 1)

Revision ID: 015_user_profile_facts
Revises: 014_gate1_identity_profile_extensions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015_user_profile_facts"
down_revision: Union[str, None] = "014_gate1_identity_profile_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profile_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_profile_facts_user_id", "user_profile_facts", ["user_id"])
    op.create_index("ix_user_profile_facts_fact_type", "user_profile_facts", ["fact_type"])


def downgrade() -> None:
    op.drop_index("ix_user_profile_facts_fact_type", table_name="user_profile_facts")
    op.drop_index("ix_user_profile_facts_user_id", table_name="user_profile_facts")
    op.drop_table("user_profile_facts")
