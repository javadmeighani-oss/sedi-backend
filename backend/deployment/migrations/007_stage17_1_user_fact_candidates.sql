-- Migration: Stage 17.1 Lifestyle Intelligence - user_fact_candidates
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS

BEGIN;

CREATE TABLE IF NOT EXISTS public.user_fact_candidates (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    domain VARCHAR(50) NOT NULL,
    key VARCHAR(255) NOT NULL,
    value_json TEXT NOT NULL,
    source_memory_id INTEGER NULL,
    confidence FLOAT NOT NULL DEFAULT 0.5,
    is_explicit BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_user_fact_candidates_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_fact_candidates_memory FOREIGN KEY (source_memory_id) REFERENCES public.memory(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_user_fact_candidates_user_status_created
  ON public.user_fact_candidates (user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_user_fact_candidates_user_domain
  ON public.user_fact_candidates (user_id, domain);

COMMIT;
