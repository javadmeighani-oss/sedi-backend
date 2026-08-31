"""I10-B06 migration 076 upgrade/downgrade/re-upgrade PostgreSQL validation."""

from __future__ import annotations

from alembic import command
from sqlalchemy import text

from backend.tests.helpers.i10_postgresql_harness import (
    I10IsolatedPgDb,
    _REV_075,
    _REV_076,
    pg_column_exists,
)


def test_migration_076_cycle_upgrade_downgrade_reupgrade():
    isolated = I10IsolatedPgDb.create(suffix="i10mig076", revision=_REV_075)
    try:
        assert isolated.head() == _REV_075
        with isolated.engine.begin() as conn:
            intent_id = conn.execute(
                text(
                    """
                    INSERT INTO users (name, secret_key, preferred_language, phone, created_at)
                    VALUES ('I10Mig076Owner', 'sk-076', 'en', '+10000003001', NOW())
                    RETURNING id
                    """
                )
            ).scalar_one()
            cg_id = conn.execute(
                text(
                    """
                    INSERT INTO user_caregivers (
                        owner_user_id, name, priority, notify_emergency,
                        notify_daily_status, notify_care_summary, notify_vital_alerts,
                        can_manage_profile, is_active, created_at, updated_at
                    )
                    VALUES (:oid, 'Relative', 0, true, false, false, false, false, true, NOW(), NOW())
                    RETURNING id
                    """
                ),
                {"oid": intent_id},
            ).scalar_one()
            legacy_id = conn.execute(
                text(
                    """
                    INSERT INTO caregiver_notification_intents (
                        owner_user_id, caregiver_id, notification_type, status, dedupe_key, created_at
                    )
                    VALUES (:oid, :cg, 'important_vital_alert', 'suppressed', 'legacy-dedupe-076', NOW())
                    RETURNING id
                    """
                ),
                {"oid": intent_id, "cg": cg_id},
            ).scalar_one()
            assert not pg_column_exists(conn, "caregiver_notification_intents", "health_subject_id")

        command.upgrade(isolated.cfg, _REV_076)
        assert isolated.head() == _REV_076

        with isolated.engine.connect() as conn:
            assert pg_column_exists(conn, "caregiver_notification_intents", "health_subject_id")
            status = conn.execute(
                text("SELECT status FROM caregiver_notification_intents WHERE id = :id"),
                {"id": legacy_id},
            ).scalar_one()
            assert status == "suppressed"

        command.downgrade(isolated.cfg, _REV_075)
        assert isolated.head() == _REV_075

        with isolated.engine.connect() as conn:
            assert not pg_column_exists(conn, "caregiver_notification_intents", "health_subject_id")

        command.upgrade(isolated.cfg, _REV_076)
        assert isolated.head() == _REV_076
    finally:
        isolated.close()
