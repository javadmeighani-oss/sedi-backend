"""DB-03 Wave 0 — drift normalization

Revision ID: 057_db03_w0_drift_normalization
Revises: 056_i5_w2_p02_conflict_safety

MIG-DB03-W0 — §270.P / §270.Q
- DROP duplicate medications_condition_id_fkey; KEEP fk_medications_condition_id
- Align memory.user_id ON DELETE CASCADE (Production-matched product rule)
- Stage17 pgvector/rag_embeddings remains NONCANONICAL (no install here)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "057_db03_w0_drift_normalization"
down_revision: Union[str, None] = "056_i5_w2_p02_conflict_safety"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'medications_condition_id_fkey'
      AND conrelid = 'public.medications'::regclass
  ) THEN
    ALTER TABLE medications DROP CONSTRAINT medications_condition_id_fkey;
  END IF;
END $$;
"""
    )
    # Ensure named FK exists (idempotent; created by 003 historically).
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_medications_condition_id'
  ) THEN
    ALTER TABLE medications
      ADD CONSTRAINT fk_medications_condition_id
      FOREIGN KEY (condition_id) REFERENCES medical_conditions(id) ON DELETE SET NULL;
  END IF;
END $$;
"""
    )
    # Align memory.user_id delete behavior with Production CASCADE.
    op.execute(
        """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT c.conname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'memory'
      AND c.contype = 'f'
      AND pg_get_constraintdef(c.oid) ILIKE '%users%'
  LOOP
    EXECUTE format('ALTER TABLE memory DROP CONSTRAINT %I', r.conname);
  END LOOP;
  ALTER TABLE memory
    ADD CONSTRAINT fk_memory_user_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
END $$;
"""
    )


def downgrade() -> None:
    # Downgrade restores a non-CASCADE FK name without reintroducing the duplicate.
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_memory_user_id') THEN
    ALTER TABLE memory DROP CONSTRAINT fk_memory_user_id;
  END IF;
  ALTER TABLE memory
    ADD CONSTRAINT memory_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id);
END $$;
"""
    )
    # Do not recreate medications_condition_id_fkey (duplicate was the drift).
