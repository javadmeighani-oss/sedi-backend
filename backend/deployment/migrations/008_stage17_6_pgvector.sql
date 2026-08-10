-- ============================================================================
-- DB-03 / §270.O / §270.Q WAVE0 — NONCANONICAL HISTORICAL ARCHITECTURE
-- STATUS: DEPRECATE / DO NOT APPLY
-- Canonical retrieval metadata authority = knowledge_chunk_embeddings (EXTENDED)
-- Do NOT install pgvector via this path.
-- Do NOT create rag_embeddings as a production Alembic/ORM authority.
-- Retained as historical evidence only. CI denies treating this as active migration.
-- ============================================================================
-- Migration: Stage 17.6 Vector RAG - pgvector extension and rag_embeddings table
-- Idempotent: CREATE EXTENSION IF NOT EXISTS, CREATE TABLE IF NOT EXISTS
-- Dimension 1536 matches text-embedding-3-small (configurable in code)
-- DB-03: This file is ARCHIVED NONCANONICAL. Prefer knowledge_chunk_embeddings.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.rag_embeddings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_rag_embeddings_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT uq_rag_embeddings_user_type_source UNIQUE (user_id, source_type, source_id)
);

CREATE INDEX IF NOT EXISTS ix_rag_embeddings_user_type
    ON public.rag_embeddings (user_id, source_type);

-- IVFFlat index: requires table to have rows. If migration fails here, run after initial data load.
-- lists=1 allows empty-table creation; increase (e.g. lists=100) after ~1000+ rows for better performance.
CREATE INDEX IF NOT EXISTS ix_rag_embeddings_embedding
    ON public.rag_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 1);

COMMIT;
