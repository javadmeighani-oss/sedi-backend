"""I10-B15-A02 owner provenance nullable contract (PostgreSQL).

Canonical law:
- SELF owner_user_id = HealthSubject.linked_user_id
- MANAGED accountless owner_user_id = NULL
- MANAGER access != owner provenance
- recipient/auth/prefs/dedupe independent of owner provenance
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from alembic import command
from sqlalchemy import text

from backend.app import models
from backend.app.services.i10.care_digest_producer_worker import (
    resolve_subject_owner_user_id,
    run_care_digest_producer_for_subject,
)
from backend.app.services.i10.care_network_access import (
    grant_caregiver_subject_access,
    revoke_caregiver_subject_access,
)
from backend.app.services.i10.care_network_grants import (
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.tests.helpers.i10_postgresql_harness import (
    I10IsolatedPgDb,
    _REV_078,
    _REV_079,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
    },
    clear=False,
)


@pytest.fixture
def a02_patches():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _push(db, user_id: int, token: str) -> None:
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=token, is_active=True))
    db.commit()


def _prefs(db, user_id: int) -> None:
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=True,
            health_alert_enabled=True,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()


def _when() -> datetime:
    return datetime(2026, 8, 31, 9, 0, 0, tzinfo=timezone.utc)


def _rollup(db, actor: models.User, subject: models.HealthSubject, when: datetime) -> None:
    start = datetime(when.year, when.month, when.day, tzinfo=timezone.utc)
    db.add(
        models.PhysiologicalMeasurementRollup(
            user_id=actor.id,
            health_subject_id=subject.id,
            measurement_type="heart_rate",
            bucket_kind="daily",
            bucket_start=start,
            bucket_end=when - timedelta(hours=2),
            sample_count=12,
            avg_value=78.0,
            coverage=0.85,
        )
    )
    db.commit()


def test_migration_079_cycle_and_nullable_owner():
    isolated = I10IsolatedPgDb.create(suffix="i10a02mig", revision=_REV_078)
    try:
        assert isolated.head() == _REV_078
        with isolated.engine.begin() as conn:
            uid = conn.execute(
                text(
                    """
                    INSERT INTO users (name, secret_key, preferred_language, phone, created_at)
                    VALUES ('A02Owner', 'sk-a02', 'en', '+10000004001', NOW())
                    RETURNING id
                    """
                )
            ).scalar_one()
            conn.execute(
                text(
                    """
                    INSERT INTO caregiver_notification_intents (
                        owner_user_id, caregiver_id, notification_type, status, dedupe_key, created_at
                    )
                    VALUES (:oid, NULL, 'legacy', 'suppressed', 'a02-legacy-nonnull', NOW())
                    """
                ),
                {"oid": uid},
            )
        command.upgrade(isolated.cfg, _REV_079)
        assert isolated.head() == _REV_079
        with isolated.engine.begin() as conn:
            nullable = conn.execute(
                text(
                    """
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'caregiver_notification_intents'
                      AND column_name = 'owner_user_id'
                    """
                )
            ).scalar_one()
            assert nullable == "YES"
            # existing non-null preserved
            existing = conn.execute(
                text(
                    "SELECT owner_user_id FROM caregiver_notification_intents WHERE dedupe_key='a02-legacy-nonnull'"
                )
            ).scalar_one()
            assert existing is not None
            # new NULL provenance row valid
            conn.execute(
                text(
                    """
                    INSERT INTO caregiver_notification_intents (
                        owner_user_id, caregiver_id, notification_type, status, dedupe_key, created_at
                    )
                    VALUES (NULL, NULL, 'i10_care_network', 'pending', 'a02-null-owner', NOW())
                    """
                )
            )
            null_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM caregiver_notification_intents WHERE owner_user_id IS NULL"
                )
            ).scalar_one()
            assert null_count == 1
        # downgrade blocked while NULL rows exist
        with pytest.raises(Exception):
            command.downgrade(isolated.cfg, _REV_078)
        assert isolated.head() == _REV_079
        with isolated.engine.begin() as conn:
            conn.execute(text("DELETE FROM caregiver_notification_intents WHERE owner_user_id IS NULL"))
        command.downgrade(isolated.cfg, _REV_078)
        assert isolated.head() == _REV_078
        command.upgrade(isolated.cfg, _REV_079)
        assert isolated.head() == _REV_079
    finally:
        isolated.close()


def test_self_owner_provenance_not_unrelated_manager(db, a02_patches):
    patient = _user(db, "self-patient")
    manager = _user(db, "unrelated-manager")
    self_hs = ensure_self_subject_for_account(db, patient.id, commit=True)
    # Unrelated manager access must not become owner provenance
    grant_caregiver_subject_access(
        db,
        actor_user_id=patient.id,
        health_subject_id=self_hs.id,
        recipient_account_user_id=manager.id,
        access_role="MANAGER",
        commit=True,
    )
    assert resolve_subject_owner_user_id(db, self_hs.id) == patient.id
    assert resolve_subject_owner_user_id(db, self_hs.id) != manager.id


def test_managed_mother_null_owner_son_recipient(db, a02_patches):
    son = _user(db, "son-mgr")
    stranger = _user(db, "stranger")
    mother = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="Mother ALS", access_role="MANAGER"
    )
    assert mother.linked_user_id is None
    assert resolve_subject_owner_user_id(db, mother.id) is None

    create_subject_notification_grant(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        commit=True,
    )
    _prefs(db, son.id)
    _push(db, son.id, "tok-son-a02")
    _rollup(db, son, mother, _when())

    outcome = run_care_digest_producer_for_subject(
        db, health_subject_id=mother.id, when=_when(), deliver=True, commit=True
    )
    assert outcome.get("status") != "dormant"
    intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .all()
    )
    assert len(intents) >= 1
    for intent in intents:
        assert intent.owner_user_id is None
        assert intent.health_subject_id == mother.id
        assert intent.recipient_user_id == son.id
        assert intent.recipient_user_id != stranger.id

    # no fake Mother Account
    assert mother.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == "Mother ALS").count() == 0

    # unauthorized stranger blocked
    assert all(i.recipient_user_id != stranger.id for i in intents)

    # delivery-time revalidation + prefs path
    for intent in intents:
        if intent.status == "pending":
            result = process_caregiver_delivery_intent(db, intent, commit=True)
            assert result["status"] in ("processed", "suppressed", "idempotent")

    # revoke fail-closed: revoke grant then access while Son still manages
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        commit=True,
    )
    before = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.health_subject_id == mother.id)
        .count()
    )
    run_care_digest_producer_for_subject(
        db,
        health_subject_id=mother.id,
        when=_when() + timedelta(days=1),
        deliver=False,
        commit=True,
    )
    after = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.health_subject_id == mother.id)
        .count()
    )
    assert after == before  # no new intents without grant
    revoke_caregiver_subject_access(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_account_user_id=son.id,
        commit=True,
    )


def test_alembic_single_head_is_079():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("backend/alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [_REV_079]


def test_cni_owner_column_nullable_in_orm():
    col = models.CaregiverNotificationIntent.__table__.c.owner_user_id
    assert col.nullable is True
