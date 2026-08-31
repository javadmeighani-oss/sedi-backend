"""I10 medication adherence foundation (PD-I10-B09).

Revision ID: 077_i10_medication_adherence_foundation
Revises: 076_i10_care_network_delivery_foundation

Per-dose occurrence/adherence rows for truthful medication reminder state.
No backfill. No automatic TAKEN/MISSED inference.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "077_i10_medication_adherence_foundation"
down_revision: Union[str, None] = "076_i10_care_network_delivery_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE medication_dose_occurrences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    user_medication_id INTEGER NOT NULL,
    schedule_id INTEGER,
    scheduled_for TIMESTAMPTZ NOT NULL,
    occurrence_key VARCHAR(255) NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'DUE',
    confirmed_at TIMESTAMPTZ,
    confirmation_source VARCHAR(64),
    source_notification_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_mdo_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_mdo_user_medication_id FOREIGN KEY (user_medication_id) REFERENCES user_medications(id) ON DELETE CASCADE,
    CONSTRAINT fk_mdo_schedule_id FOREIGN KEY (schedule_id) REFERENCES user_medication_schedules(id) ON DELETE SET NULL,
    CONSTRAINT fk_mdo_source_notification_id FOREIGN KEY (source_notification_id) REFERENCES notifications(id) ON DELETE SET NULL,
    CONSTRAINT uq_mdo_user_occurrence_key UNIQUE (user_id, occurrence_key),
    CONSTRAINT ck_mdo_state CHECK (state IN ('DUE', 'CONFIRMED_TAKEN', 'UNKNOWN', 'MISSED'))
);
"""
    )
    op.execute("CREATE INDEX ix_mdo_user_medication_id ON medication_dose_occurrences (user_medication_id);")
    op.execute("CREATE INDEX ix_mdo_source_notification_id ON medication_dose_occurrences (source_notification_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS medication_dose_occurrences CASCADE;")
