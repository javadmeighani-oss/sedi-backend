"""SCIS-01: pgvector + KCE foundation + FTS (rehearsal/CI only — no Production apply).

Revision ID: 061_scis01_pgvector_kce_foundation
Revises: 060_db03_w4_w6_scale_inspect_roles

SCIS-01 / ADR-RAG-003:
- CREATE EXTENSION vector (pgvector)
- Extend knowledge_chunk_embeddings for PGVECTOR backend + FTS
- Exact cosine distance queries (<=>); NO HNSW/IVFFlat for V1 scale (ANN deferred)
- Stage17 rag_embeddings remains NONCANONICAL / not created
"""

from typing import Sequence, Union

from alembic import op


revision: str = "061_scis01_pgvector_kce_foundation"
down_revision: Union[str, None] = "060_db03_w4_w6_scale_inspect_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        "ALTER TABLE knowledge_chunk_embeddings DROP CONSTRAINT IF EXISTS ck_kce_backend_kind_vocab"
    )
    op.execute(
        """
ALTER TABLE knowledge_chunk_embeddings
  ADD CONSTRAINT ck_kce_backend_kind_vocab
  CHECK (backend_kind IS NULL OR backend_kind IN (
    'JSON_INLINE', 'EXTERNAL_VECTOR_DEFERRED', 'PGVECTOR'
  ))
"""
    )

    op.execute(
        "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector(1024)"
    )
    op.execute(
        "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS embedding_model_version VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS chunker_version VARCHAR(64)"
    )
    op.execute(
        """
ALTER TABLE knowledge_chunk_embeddings
  ADD COLUMN IF NOT EXISTS chunk_version INTEGER DEFAULT 1 NOT NULL
"""
    )
    op.execute("ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS section_path TEXT")
    op.execute(
        "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS content_language VARCHAR(16)"
    )
    op.execute("ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS search_document TEXT")
    op.execute("ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS search_tsv tsvector")

    op.execute(
        """
CREATE INDEX IF NOT EXISTS ix_kce_search_tsv
  ON knowledge_chunk_embeddings USING gin (search_tsv)
"""
    )
    # Exact search for V1; ANN (HNSW) deferred pending scale evidence (ADR-RAG-003).
    op.execute(
        """
COMMENT ON COLUMN knowledge_chunk_embeddings.embedding_vector IS
'SCIS-01 pgvector column (1024-d). Exact <=> search; HNSW/IVFFlat not enabled in V1.';
"""
    )
    op.execute(
        """
COMMENT ON TABLE knowledge_chunk_embeddings IS
'Canonical retrieval index metadata. RAG INDEX != SOURCE OF TRUTH. Rebuildable. SCIS-01 adds PGVECTOR+FTS.';
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kce_search_tsv")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS search_tsv")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS search_document")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS content_language")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS section_path")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS chunk_version")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS chunker_version")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS embedding_model_version")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS embedding_provider")
    op.execute("ALTER TABLE knowledge_chunk_embeddings DROP COLUMN IF EXISTS embedding_vector")
    op.execute(
        "ALTER TABLE knowledge_chunk_embeddings DROP CONSTRAINT IF EXISTS ck_kce_backend_kind_vocab"
    )
    op.execute(
        """
ALTER TABLE knowledge_chunk_embeddings
  ADD CONSTRAINT ck_kce_backend_kind_vocab
  CHECK (backend_kind IS NULL OR backend_kind IN ('JSON_INLINE', 'EXTERNAL_VECTOR_DEFERRED'))
"""
    )
    # Extension left installed (shared); not dropped on downgrade.
