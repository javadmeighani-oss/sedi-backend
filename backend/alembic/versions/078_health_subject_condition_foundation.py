"""C04 HealthSubjectCondition + managed-person create idempotency.

Revision ID: 078_health_subject_condition_foundation
Revises: 077_i10_medication_adherence_foundation

Patient-specific clinical condition authority bound to HealthSubject.
Optional create idempotency keys for managed HealthSubject retry safety.
No UserCondition backfill. No production mutation.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "078_health_subject_condition_foundation"
down_revision: Union[str, None] = "077_i10_medication_adherence_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE health_subjects
    ADD COLUMN IF NOT EXISTS created_by_account_user_id INTEGER NULL,
    ADD COLUMN IF NOT EXISTS creation_idempotency_key VARCHAR(128) NULL;
"""
    )
    op.execute(
        """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_hs_created_by_account_user_id'
    ) THEN
        ALTER TABLE health_subjects
            ADD CONSTRAINT fk_hs_created_by_account_user_id
            FOREIGN KEY (created_by_account_user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;
"""
    )
    op.execute(
        """
CREATE UNIQUE INDEX IF NOT EXISTS uq_hs_creator_idempotency
    ON health_subjects (created_by_account_user_id, creation_idempotency_key)
    WHERE creation_idempotency_key IS NOT NULL;
"""
    )

    op.execute(
        """
CREATE TABLE health_subject_conditions (
    id SERIAL PRIMARY KEY,
    health_subject_id INTEGER NOT NULL,
    condition_id INTEGER NOT NULL,
    reported_by_account_user_id INTEGER NULL,
    source_class VARCHAR(32) NOT NULL,
    verification_state VARCHAR(32) NOT NULL DEFAULT 'REPORTED_UNVERIFIED',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    severity VARCHAR(64) NULL,
    notes TEXT NULL,
    diagnosed_date TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_hsc_health_subject_id
        FOREIGN KEY (health_subject_id) REFERENCES health_subjects(id) ON DELETE CASCADE,
    CONSTRAINT fk_hsc_condition_id
        FOREIGN KEY (condition_id) REFERENCES medical_conditions(id) ON DELETE RESTRICT,
    CONSTRAINT fk_hsc_reported_by_account_user_id
        FOREIGN KEY (reported_by_account_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT ck_hsc_source_class CHECK (
        source_class IN (
            'SELF_REPORTED',
            'CAREGIVER_REPORTED',
            'CLINICAL',
            'IMPORTED',
            'SYSTEM_SUGGESTED'
        )
    ),
    CONSTRAINT ck_hsc_verification_state CHECK (
        verification_state IN (
            'REPORTED_UNVERIFIED',
            'VERIFIED',
            'DISPUTED',
            'UNKNOWN'
        )
    ),
    CONSTRAINT ck_hsc_status CHECK (status IN ('active', 'retracted'))
);
"""
    )
    op.execute(
        """
CREATE UNIQUE INDEX uq_hsc_active_subject_condition
    ON health_subject_conditions (health_subject_id, condition_id)
    WHERE status = 'active';
"""
    )
    op.execute(
        "CREATE INDEX ix_hsc_health_subject_id ON health_subject_conditions (health_subject_id);"
    )
    op.execute(
        "CREATE INDEX ix_hsc_reported_by_account_user_id ON health_subject_conditions (reported_by_account_user_id);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS health_subject_conditions CASCADE;")
    op.execute("DROP INDEX IF EXISTS uq_hs_creator_idempotency;")
    op.execute(
        """
ALTER TABLE health_subjects
    DROP CONSTRAINT IF EXISTS fk_hs_created_by_account_user_id;
"""
    )
    op.execute(
        """
ALTER TABLE health_subjects
    DROP COLUMN IF EXISTS creation_idempotency_key,
    DROP COLUMN IF EXISTS created_by_account_user_id;
"""
    )
