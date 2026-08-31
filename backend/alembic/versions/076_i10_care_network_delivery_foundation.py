"""I10 care network delivery foundation (PD-I10-B06).

Revision ID: 076_i10_care_network_delivery_foundation
Revises: 075_i10_care_network_identity_grants

Additive extension to caregiver_notification_intents for subject-scoped I10 delivery.
Legacy rows unchanged. No backfill. caregiver_id nullable for account-only intents.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "076_i10_care_network_delivery_foundation"
down_revision: Union[str, None] = "075_i10_care_network_identity_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ADD COLUMN health_subject_id INTEGER,
    ADD COLUMN notification_scope VARCHAR(64),
    ADD COLUMN occurrence_key VARCHAR(255),
    ADD COLUMN semantic_family VARCHAR(64),
    ADD COLUMN privacy_class VARCHAR(32),
    ADD COLUMN recipient_user_id INTEGER,
    ADD COLUMN expires_at TIMESTAMPTZ,
    ADD COLUMN i10_decision_id BIGINT,
    ADD COLUMN notification_id INTEGER;
"""
    )
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ALTER COLUMN caregiver_id DROP NOT NULL;
"""
    )
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ADD CONSTRAINT fk_cni_health_subject_id
        FOREIGN KEY (health_subject_id) REFERENCES health_subjects(id) ON DELETE CASCADE;
"""
    )
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ADD CONSTRAINT fk_cni_recipient_user_id
        FOREIGN KEY (recipient_user_id) REFERENCES users(id) ON DELETE CASCADE;
"""
    )
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ADD CONSTRAINT fk_cni_i10_decision_id
        FOREIGN KEY (i10_decision_id) REFERENCES i10_notification_decisions(id) ON DELETE SET NULL;
"""
    )
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ADD CONSTRAINT fk_cni_notification_id
        FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL;
"""
    )
    op.execute(
        """CREATE INDEX ix_cni_health_subject_id ON caregiver_notification_intents (health_subject_id);"""
    )
    op.execute(
        """CREATE INDEX ix_cni_recipient_user_id ON caregiver_notification_intents (recipient_user_id);"""
    )
    op.execute(
        """
CREATE INDEX ix_cni_i10_pending
ON caregiver_notification_intents (status, health_subject_id)
WHERE health_subject_id IS NOT NULL AND status = 'pending';
"""
    )


def downgrade() -> None:
    op.execute("""DROP INDEX IF EXISTS ix_cni_i10_pending;""")
    op.execute("""DROP INDEX IF EXISTS ix_cni_recipient_user_id;""")
    op.execute("""DROP INDEX IF EXISTS ix_cni_health_subject_id;""")
    op.execute("""ALTER TABLE caregiver_notification_intents DROP CONSTRAINT IF EXISTS fk_cni_notification_id;""")
    op.execute("""ALTER TABLE caregiver_notification_intents DROP CONSTRAINT IF EXISTS fk_cni_i10_decision_id;""")
    op.execute("""ALTER TABLE caregiver_notification_intents DROP CONSTRAINT IF EXISTS fk_cni_recipient_user_id;""")
    op.execute("""ALTER TABLE caregiver_notification_intents DROP CONSTRAINT IF EXISTS fk_cni_health_subject_id;""")
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    DROP COLUMN IF EXISTS notification_id,
    DROP COLUMN IF EXISTS i10_decision_id,
    DROP COLUMN IF EXISTS expires_at,
    DROP COLUMN IF EXISTS recipient_user_id,
    DROP COLUMN IF EXISTS privacy_class,
    DROP COLUMN IF EXISTS semantic_family,
    DROP COLUMN IF EXISTS occurrence_key,
    DROP COLUMN IF EXISTS notification_scope,
    DROP COLUMN IF EXISTS health_subject_id;
"""
    )
