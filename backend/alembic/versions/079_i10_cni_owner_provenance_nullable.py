"""B15-A02 CaregiverNotificationIntent owner_user_id nullable provenance.

Revision ID: 079_i10_cni_owner_provenance_nullable
Revises: 078_health_subject_condition_foundation

Makes caregiver_notification_intents.owner_user_id nullable so accountless
MANAGED HealthSubjects can carry NULL owner provenance without fabricating a
MANAGER Account as subject owner.

Authorization/recipient/prefs/dedupe remain on health_subject_id +
recipient_user_id + access/grant chains — not this column.
No production mutation.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "079_i10_cni_owner_provenance_nullable"
down_revision: Union[str, None] = "078_health_subject_condition_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ALTER COLUMN owner_user_id DROP NOT NULL;
"""
    )


def downgrade() -> None:
    # Fail closed: refuse downgrade while NULL provenance rows exist.
    op.execute(
        """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM caregiver_notification_intents WHERE owner_user_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'DOWNGRADE_079_BLOCKED: NULL owner_user_id rows exist; cannot restore NOT NULL';
    END IF;
END $$;
"""
    )
    op.execute(
        """
ALTER TABLE caregiver_notification_intents
    ALTER COLUMN owner_user_id SET NOT NULL;
"""
    )
