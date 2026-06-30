"""knowledge_ingestion_runs (Gate 3 KB ingest audit)

Revision ID: 030_knowledge_ingestion_runs
Revises: 029_knowledge_chunks
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "030_knowledge_ingestion_runs"
down_revision: Union[str, None] = "029_knowledge_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_ingestion_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("chunks_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("run_by", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_ingestion_runs_source_id", "knowledge_ingestion_runs", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_ingestion_runs_source_id", table_name="knowledge_ingestion_runs")
    op.drop_table("knowledge_ingestion_runs")
