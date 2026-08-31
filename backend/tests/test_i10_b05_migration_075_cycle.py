"""I10-B05 migration 075 upgrade/downgrade/re-upgrade PostgreSQL validation."""

from __future__ import annotations

from alembic import command
from sqlalchemy import text

from backend.tests.helpers.i10_postgresql_harness import (
    I10IsolatedPgDb,
    _REV_074,
    _REV_075,
    pg_column_exists,
)


def test_migration_075_cycle_upgrade_downgrade_reupgrade():
    isolated = I10IsolatedPgDb.create(suffix="i10mig075", revision=_REV_074)
    try:
        assert isolated.head() == _REV_074

        with isolated.engine.begin() as conn:
            owner_id = conn.execute(
                text(
                    """
                    INSERT INTO users (name, secret_key, preferred_language, phone, created_at)
                    VALUES ('I10Mig075Owner', 'sk-i10-075', 'en', '+10000002001', NOW())
                    RETURNING id
                    """
                )
            ).scalar_one()
            caregiver_row_id = conn.execute(
                text(
                    """
                    INSERT INTO user_caregivers (
                        owner_user_id, name, phone, priority,
                        notify_daily_status, notify_emergency, notify_care_summary,
                        notify_vital_alerts, can_manage_profile, is_active, created_at, updated_at
                    )
                    VALUES (
                        :owner_id, 'Relative', '+10000002002', 0,
                        false, true, false, false, false, true, NOW(), NOW()
                    )
                    RETURNING id
                    """
                ),
                {"owner_id": owner_id},
            ).scalar_one()
            assert not pg_column_exists(conn, "user_caregivers", "linked_account_user_id")

        command.upgrade(isolated.cfg, _REV_075)
        assert isolated.head() == _REV_075

        with isolated.engine.connect() as conn:
            assert pg_column_exists(conn, "user_caregivers", "linked_account_user_id")
            assert pg_column_exists(conn, "user_caregivers", "health_subject_id")
            link = conn.execute(
                text("SELECT linked_account_user_id FROM user_caregivers WHERE id = :id"),
                {"id": caregiver_row_id},
            ).scalar_one()
            assert link is None

        command.downgrade(isolated.cfg, _REV_074)
        assert isolated.head() == _REV_074

        with isolated.engine.connect() as conn:
            assert not pg_column_exists(conn, "user_caregivers", "linked_account_user_id")
            name = conn.execute(
                text("SELECT name FROM user_caregivers WHERE id = :id"),
                {"id": caregiver_row_id},
            ).scalar_one()
            assert name == "Relative"

        command.upgrade(isolated.cfg, _REV_075)
        assert isolated.head() == _REV_075

        with isolated.engine.connect() as conn:
            assert pg_column_exists(conn, "user_caregivers", "linked_account_user_id")
    finally:
        isolated.close()
