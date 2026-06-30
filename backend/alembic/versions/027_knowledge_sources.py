"""knowledge_sources (Gate 3 curated KB registry)

Revision ID: 027_knowledge_sources
Revises: 026_gate2_legacy_backfill_optional
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "027_knowledge_sources"
down_revision: Union[str, None] = "026_gate2_legacy_backfill_optional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="other"),
        sa.Column("trust_level", sa.String(length=32), nullable=False, server_default="editorial"),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="fa"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("freshness_policy_days", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("ingestion_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("license_notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_knowledge_sources_slug"),
    )
    op.create_index("ix_knowledge_sources_category", "knowledge_sources", ["category"])
    op.create_index("ix_knowledge_sources_ingestion_status", "knowledge_sources", ["ingestion_status"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_sources_ingestion_status", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_category", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
