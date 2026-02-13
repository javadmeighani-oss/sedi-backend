"""add medications condition_id

Revision ID: 003_medications_condition_id
Revises: 002_phone_otp
Create Date: 2025-02-13

Add nullable condition_id FK to medications (production had table without this column).
Safe to run if column/constraint/index already exist (IF NOT EXISTS / IF EXISTS).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_medications_condition_id"
down_revision: Union[str, None] = "002_phone_otp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column only if missing (production may have medications without it)
    op.execute(
        sa.text("ALTER TABLE medications ADD COLUMN IF NOT EXISTS condition_id INTEGER NULL")
    )
    # Add FK only if not already present
    op.execute(
        sa.text("""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_medications_condition_id') THEN
            ALTER TABLE medications
              ADD CONSTRAINT fk_medications_condition_id
              FOREIGN KEY (condition_id) REFERENCES medical_conditions(id) ON DELETE SET NULL;
          END IF;
        END $$;
        """)
    )
    # Index for condition_id (optional but recommended for joins)
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_medications_condition_id ON medications (condition_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE medications DROP CONSTRAINT IF EXISTS fk_medications_condition_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_medications_condition_id"))
    op.execute(sa.text("ALTER TABLE medications DROP COLUMN IF EXISTS condition_id"))
