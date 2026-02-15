"""knowledge_capture_v1 (Knowledge Capture V1)

Revision ID: 004_knowledge_capture_v1
Revises: 003_medications_condition_id
Create Date: 2025-02-15

Knowledge Capture V1: user_profile_core, kc_fact_candidates, kc_user_facts.
Additive migration; does not modify existing user_fact_candidates/user_facts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004_knowledge_capture_v1"
down_revision: Union[str, None] = "003_medications_condition_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) user_profile_core (1 row per user)
    op.create_table(
        "user_profile_core",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(length=32), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("quiet_start", sa.Time(), nullable=True),
        sa.Column("quiet_end", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_profile_core_user_id"), "user_profile_core", ["user_id"], unique=True)

    # 2) kc_fact_candidates (Knowledge Capture candidates; distinct from user_fact_candidates)
    op.create_table(
        "kc_fact_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),  # chat, form, import
        sa.Column("fact_type", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),  # pending, accepted, rejected
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kc_fact_candidates_id"), "kc_fact_candidates", ["id"], unique=False)
    op.create_index(op.f("ix_kc_fact_candidates_user_id"), "kc_fact_candidates", ["user_id"], unique=False)
    op.create_index(op.f("ix_kc_fact_candidates_status"), "kc_fact_candidates", ["status"], unique=False)

    # 3) kc_user_facts (Knowledge Capture verified facts; distinct from user_facts)
    op.create_table(
        "kc_user_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("verified_by", sa.String(length=32), nullable=False),  # user, system, clinician
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kc_user_facts_id"), "kc_user_facts", ["id"], unique=False)
    op.create_index(op.f("ix_kc_user_facts_user_id"), "kc_user_facts", ["user_id"], unique=False)
    op.create_index(op.f("ix_kc_user_facts_fact_type"), "kc_user_facts", ["fact_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_kc_user_facts_fact_type"), table_name="kc_user_facts")
    op.drop_index(op.f("ix_kc_user_facts_user_id"), table_name="kc_user_facts")
    op.drop_index(op.f("ix_kc_user_facts_id"), table_name="kc_user_facts")
    op.drop_table("kc_user_facts")
    op.drop_index(op.f("ix_kc_fact_candidates_status"), table_name="kc_fact_candidates")
    op.drop_index(op.f("ix_kc_fact_candidates_user_id"), table_name="kc_fact_candidates")
    op.drop_index(op.f("ix_kc_fact_candidates_id"), table_name="kc_fact_candidates")
    op.drop_table("kc_fact_candidates")
    op.drop_index(op.f("ix_user_profile_core_user_id"), table_name="user_profile_core")
    op.drop_table("user_profile_core")
