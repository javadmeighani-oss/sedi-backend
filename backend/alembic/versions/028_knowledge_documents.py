"""knowledge_documents (Gate 3 curated KB documents)

Revision ID: 028_knowledge_documents
Revises: 027_knowledge_sources
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "028_knowledge_documents"
down_revision: Union[str, None] = "027_knowledge_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="other"),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="fa"),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("specialty", sa.String(length=128), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_source_id", "knowledge_documents", ["source_id"])
    op.create_index("ix_knowledge_documents_category", "knowledge_documents", ["category"])
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])
    op.create_index(
        "ix_knowledge_documents_status_category",
        "knowledge_documents",
        ["status", "category"],
    )
    op.create_index(
        "ix_knowledge_documents_source_status",
        "knowledge_documents",
        ["source_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_source_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_status_category", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_category", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_source_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
