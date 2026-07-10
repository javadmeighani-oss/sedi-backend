"""Section 10 — KB chunk embedding metadata and memory governance fields

Revision ID: 049_section10_kb_embeddings_memory_governance
Revises: 048_section10_medication_inventory
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "049_section10_kb_embeddings_memory_governance"
down_revision: Union[str, None] = "048_section10_medication_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunk_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("model_identifier", sa.String(length=128), nullable=False),
        sa.Column("vector_dimension", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "model_identifier", name="uq_kb_chunk_embeddings_chunk_model"),
    )
    op.create_index("ix_knowledge_chunk_embeddings_chunk_id", "knowledge_chunk_embeddings", ["chunk_id"])
    op.create_index("ix_knowledge_chunk_embeddings_status", "knowledge_chunk_embeddings", ["embedding_status"])

    op.add_column("user_memory_facts", sa.Column("provenance", sa.String(length=64), nullable=True))
    op.add_column("user_memory_facts", sa.Column("source_interaction_id", sa.Integer(), nullable=True))
    op.add_column("user_memory_facts", sa.Column("extracted_at", sa.DateTime(), nullable=True))
    op.add_column("user_memory_facts", sa.Column("valid_from", sa.DateTime(), nullable=True))
    op.add_column("user_memory_facts", sa.Column("valid_until", sa.DateTime(), nullable=True))
    op.add_column("user_memory_facts", sa.Column("last_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("user_memory_facts", sa.Column("supersedes_fact_id", sa.Integer(), nullable=True))
    op.add_column(
        "user_memory_facts",
        sa.Column("fact_status", sa.String(length=32), nullable=False, server_default="active"),
    )


def downgrade() -> None:
    op.drop_column("user_memory_facts", "fact_status")
    op.drop_column("user_memory_facts", "supersedes_fact_id")
    op.drop_column("user_memory_facts", "last_confirmed_at")
    op.drop_column("user_memory_facts", "valid_until")
    op.drop_column("user_memory_facts", "valid_from")
    op.drop_column("user_memory_facts", "extracted_at")
    op.drop_column("user_memory_facts", "source_interaction_id")
    op.drop_column("user_memory_facts", "provenance")
    op.drop_index("ix_knowledge_chunk_embeddings_status", table_name="knowledge_chunk_embeddings")
    op.drop_index("ix_knowledge_chunk_embeddings_chunk_id", table_name="knowledge_chunk_embeddings")
    op.drop_table("knowledge_chunk_embeddings")
