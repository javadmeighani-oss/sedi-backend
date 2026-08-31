"""I10-B04 migration 074 upgrade/downgrade/re-upgrade PostgreSQL validation."""

from __future__ import annotations

from alembic import command
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.tests.helpers.i10_postgresql_harness import (
    I10IsolatedPgDb,
    _REV_073,
    _REV_074,
    pg_column_exists,
    pg_index_exists,
    pg_table_exists,
)


def _seed_pre074_fixtures(conn) -> dict[str, int]:
    owner_id = conn.execute(
        text(
            """
            INSERT INTO users (name, secret_key, preferred_language, phone, created_at)
            VALUES ('I10MigOwner', 'sk-i10-mig', 'en', '+10000001001', NOW())
            RETURNING id
            """
        )
    ).scalar_one()
    subject_id = conn.execute(
        text(
            """
            INSERT INTO health_subjects (display_name, linked_user_id, subject_kind, status, created_at, updated_at)
            VALUES ('I10MigParent', :owner_id, 'self', 'active', NOW(), NOW())
            RETURNING id
            """
        ),
        {"owner_id": owner_id},
    ).scalar_one()
    legacy_notif_id = conn.execute(
        text(
            """
            INSERT INTO notifications (user_id, type, body, priority, created_at)
            VALUES (:owner_id, 'morning_brief', 'legacy pre-074 body', 'normal', NOW())
            RETURNING id
            """
        ),
        {"owner_id": owner_id},
    ).scalar_one()
    rollup_id = conn.execute(
        text(
            """
            INSERT INTO physiological_measurement_rollups (
                user_id, health_subject_id, measurement_type, bucket_kind,
                bucket_start, bucket_end, sample_count, avg_value
            )
            VALUES (
                :owner_id, :subject_id, 'heart_rate', 'daily',
                TIMESTAMPTZ '2026-08-01 00:00:00+00', TIMESTAMPTZ '2026-08-02 00:00:00+00',
                1, 70.0
            )
            RETURNING id
            """
        ),
        {"owner_id": owner_id, "subject_id": subject_id},
    ).scalar_one()
    return {
        "owner_id": owner_id,
        "subject_id": subject_id,
        "legacy_notif_id": legacy_notif_id,
        "rollup_id": rollup_id,
    }


def test_migration_074_cycle_upgrade_downgrade_reupgrade():
    isolated = I10IsolatedPgDb.create(suffix="i10mig074", revision=_REV_073)
    try:
        assert isolated.head() == _REV_073

        with isolated.engine.begin() as conn:
            seeded = _seed_pre074_fixtures(conn)
            assert not pg_column_exists(conn, "notifications", "health_subject_id")
            assert not pg_table_exists(conn, "i10_notification_decisions")
            assert not pg_table_exists(conn, "health_subject_notification_grants")

        with isolated.engine.connect() as conn:
            legacy_body = conn.execute(
                text("SELECT body FROM notifications WHERE id = :id"),
                {"id": seeded["legacy_notif_id"]},
            ).scalar_one()
            rollup_avg = conn.execute(
                text("SELECT avg_value FROM physiological_measurement_rollups WHERE id = :id"),
                {"id": seeded["rollup_id"]},
            ).scalar_one()
            assert legacy_body == "legacy pre-074 body"
            assert float(rollup_avg) == 70.0

        command.upgrade(isolated.cfg, _REV_074)
        assert isolated.head() == _REV_074

        with isolated.engine.connect() as conn:
            assert pg_column_exists(conn, "notifications", "health_subject_id")
            assert pg_column_exists(conn, "notifications", "i10_policy_decision_id")
            assert pg_table_exists(conn, "i10_notification_decisions")
            assert pg_table_exists(conn, "health_subject_notification_grants")
            assert pg_index_exists(conn, "uq_i10_decision_occurrence")
            assert pg_index_exists(conn, "uq_hsng_active_subject_recipient_scope")
            legacy_hs = conn.execute(
                text("SELECT health_subject_id FROM notifications WHERE id = :id"),
                {"id": seeded["legacy_notif_id"]},
            ).scalar_one()
            assert legacy_hs is None

        SessionLocal = isolated.session_factory()
        session = SessionLocal()
        try:
            decision = models.I10NotificationDecision(
                candidate_key="mig074-cycle",
                health_subject_id=seeded["subject_id"],
                recipient_user_id=seeded["owner_id"],
                source_owner="I10_TEST",
                source_type="migration",
                source_id="1",
                semantic_family="GENERAL_STATUS",
                decision="SEND",
                reason_code="MIG074_CYCLE",
                privacy_class="PRIVATE",
            )
            session.add(decision)
            session.commit()
            decision_id = decision.id
        finally:
            session.close()

        command.downgrade(isolated.cfg, _REV_073)
        assert isolated.head() == _REV_073

        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "i10_notification_decisions")
            assert not pg_table_exists(conn, "health_subject_notification_grants")
            assert not pg_column_exists(conn, "notifications", "health_subject_id")
            legacy_body = conn.execute(
                text("SELECT body FROM notifications WHERE id = :id"),
                {"id": seeded["legacy_notif_id"]},
            ).scalar_one()
            rollup_avg = conn.execute(
                text("SELECT avg_value FROM physiological_measurement_rollups WHERE id = :id"),
                {"id": seeded["rollup_id"]},
            ).scalar_one()
            subject_owner = conn.execute(
                text("SELECT linked_user_id FROM health_subjects WHERE id = :id"),
                {"id": seeded["subject_id"]},
            ).scalar_one()
            assert legacy_body == "legacy pre-074 body"
            assert float(rollup_avg) == 70.0
            assert subject_owner == seeded["owner_id"]

        command.upgrade(isolated.cfg, _REV_074)
        assert isolated.head() == _REV_074

        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "i10_notification_decisions")
            assert pg_column_exists(conn, "notifications", "health_subject_id")
            legacy_body = conn.execute(
                text("SELECT body FROM notifications WHERE id = :id"),
                {"id": seeded["legacy_notif_id"]},
            ).scalar_one()
            rollup_avg = conn.execute(
                text("SELECT avg_value FROM physiological_measurement_rollups WHERE id = :id"),
                {"id": seeded["rollup_id"]},
            ).scalar_one()
            assert legacy_body == "legacy pre-074 body"
            assert float(rollup_avg) == 70.0
            restored_decisions = conn.execute(text("SELECT COUNT(*) FROM i10_notification_decisions")).scalar_one()
            assert restored_decisions == 0
            _ = decision_id  # 074-owned row removed on downgrade; table restored empty on re-upgrade
    finally:
        isolated.close()
