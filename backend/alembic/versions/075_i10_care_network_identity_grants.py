"""I10 care network identity / profile-account linkage foundation (PD-I10-B05).

Revision ID: 075_i10_care_network_identity_grants
Revises: 074_i10_notification_domain_foundation

Additive only on user_caregivers:
- linked_account_user_id: nullable FK to users (explicit Sedi account resolution)
- linked_at / link_provenance: resolution metadata (no phone auto-link)
- health_subject_id: optional profile→subject association metadata (not authorization)

No backfill. No phone-based account linkage. No HealthSubject access or grant mutation.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "075_i10_care_network_identity_grants"
down_revision: Union[str, None] = "074_i10_notification_domain_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE user_caregivers
    ADD COLUMN linked_account_user_id INTEGER,
    ADD COLUMN linked_at TIMESTAMPTZ,
    ADD COLUMN link_provenance VARCHAR(64),
    ADD COLUMN health_subject_id INTEGER;
"""
    )
    op.execute(
        """
ALTER TABLE user_caregivers
    ADD CONSTRAINT fk_uc_linked_account_user_id
        FOREIGN KEY (linked_account_user_id) REFERENCES users(id) ON DELETE SET NULL;
"""
    )
    op.execute(
        """
ALTER TABLE user_caregivers
    ADD CONSTRAINT fk_uc_health_subject_id
        FOREIGN KEY (health_subject_id) REFERENCES health_subjects(id) ON DELETE SET NULL;
"""
    )
    op.execute(
        """CREATE INDEX ix_uc_linked_account_user_id ON user_caregivers (linked_account_user_id);"""
    )
    op.execute(
        """CREATE INDEX ix_uc_health_subject_id ON user_caregivers (health_subject_id);"""
    )


def downgrade() -> None:
    op.execute("""DROP INDEX IF EXISTS ix_uc_health_subject_id;""")
    op.execute("""DROP INDEX IF EXISTS ix_uc_linked_account_user_id;""")
    op.execute("""ALTER TABLE user_caregivers DROP CONSTRAINT IF EXISTS fk_uc_health_subject_id;""")
    op.execute("""ALTER TABLE user_caregivers DROP CONSTRAINT IF EXISTS fk_uc_linked_account_user_id;""")
    op.execute(
        """
ALTER TABLE user_caregivers
    DROP COLUMN IF EXISTS health_subject_id,
    DROP COLUMN IF EXISTS link_provenance,
    DROP COLUMN IF EXISTS linked_at,
    DROP COLUMN IF EXISTS linked_account_user_id;
"""
    )
