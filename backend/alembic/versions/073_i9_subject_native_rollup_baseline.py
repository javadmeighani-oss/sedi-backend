"""I9 subject-native rollup/baseline persistence (PD-I9-V1-BASELINE-SUBJECT-NATIVE-ROLLUP-PG-CLOSURE-01).

Revision ID: 073_i9_subject_native_rollup_baseline
Revises: 072_i9_device_claim_gateway_lifecycle_foundation
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

I9_073_DOWNGRADE_BLOCKED_SUBJECT_NATIVE_NULL_USER_ROWS = (
    "I9_073_DOWNGRADE_BLOCKED_SUBJECT_NATIVE_NULL_USER_ROWS"
)

revision: str = "073_i9_subject_native_rollup_baseline"
down_revision: Union[str, None] = "072_i9_device_claim_gateway_lifecycle_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- physiological_measurement_rollups: subject-native authority ---
    op.execute("""ALTER TABLE physiological_measurement_rollups ALTER COLUMN user_id DROP NOT NULL;""")
    op.execute(
        """
CREATE UNIQUE INDEX uq_pmr_subject_type_bucket
ON physiological_measurement_rollups (health_subject_id, measurement_type, bucket_start, bucket_kind)
WHERE health_subject_id IS NOT NULL;
"""
    )

    # --- physiological_baselines: subject-native authority + audit fields ---
    op.execute("""ALTER TABLE physiological_baselines ALTER COLUMN user_id DROP NOT NULL;""")
    op.execute("""ALTER TABLE physiological_baselines ADD COLUMN IF NOT EXISTS baseline_method VARCHAR(64);""")
    op.execute("""ALTER TABLE physiological_baselines ADD COLUMN IF NOT EXISTS dispersion_value DOUBLE PRECISION;""")
    op.execute("""ALTER TABLE physiological_baselines ADD COLUMN IF NOT EXISTS valid_day_count INTEGER;""")
    op.execute(
        """
CREATE UNIQUE INDEX uq_pb_subject_type_version_window
ON physiological_baselines (health_subject_id, measurement_type, baseline_version, window_start)
WHERE health_subject_id IS NOT NULL;
"""
    )


def _assert_073_downgrade_representable() -> None:
    """Fail closed before any DDL when 072 cannot represent subject-native NULL user_id rows."""
    bind = op.get_bind()
    rollup_null = bind.execute(
        text("SELECT COUNT(*) FROM physiological_measurement_rollups WHERE user_id IS NULL")
    ).scalar_one()
    baseline_null = bind.execute(
        text("SELECT COUNT(*) FROM physiological_baselines WHERE user_id IS NULL")
    ).scalar_one()
    if rollup_null > 0 or baseline_null > 0:
        raise RuntimeError(
            f"{I9_073_DOWNGRADE_BLOCKED_SUBJECT_NATIVE_NULL_USER_ROWS} "
            f"physiological_measurement_rollups_null_user_count={rollup_null} "
            f"physiological_baselines_null_user_count={baseline_null}"
        )


def downgrade() -> None:
    _assert_073_downgrade_representable()

    op.execute("""DROP INDEX IF EXISTS uq_pb_subject_type_version_window;""")
    op.execute("""ALTER TABLE physiological_baselines DROP COLUMN IF EXISTS valid_day_count;""")
    op.execute("""ALTER TABLE physiological_baselines DROP COLUMN IF EXISTS dispersion_value;""")
    op.execute("""ALTER TABLE physiological_baselines DROP COLUMN IF EXISTS baseline_method;""")
    op.execute("""ALTER TABLE physiological_baselines ALTER COLUMN user_id SET NOT NULL;""")

    op.execute("""DROP INDEX IF EXISTS uq_pmr_subject_type_bucket;""")
    op.execute("""ALTER TABLE physiological_measurement_rollups ALTER COLUMN user_id SET NOT NULL;""")
