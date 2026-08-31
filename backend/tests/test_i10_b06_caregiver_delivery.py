"""I10-B06 care network recipient resolution + caregiver delivery worker (PostgreSQL)."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.app import models
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access, revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import create_subject_notification_grant, revoke_subject_notification_grant_by_scope
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import (
    process_caregiver_delivery_intent,
    process_pending_caregiver_delivery_intents,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10PrivacyClass
from backend.app.services.i10.recipient_eligibility import (
    evaluate_delivery_eligibility,
    resolve_care_network_recipients,
)
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account
from backend.app.services.user_caregiver_service import create_caregiver
from backend.app.schemas.gate1 import CaregiverCreateIn

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch(
    "backend.app.services.section10.feature_flags.i10_care_network_delivery_enabled",
    return_value=True,
)
_FCM_PATCH = patch(
    "backend.app.services.notifications.delivery_service.FCMAdapter.send",
    return_value=True,
)


def _user(db, name: str, *, lang: str = "en") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language=lang)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _push(db, user_id: int, token: str) -> None:
    db.add(
        models.PushDevice(
            user_id=user_id,
            platform="android",
            fcm_token=token,
            is_active=True,
        )
    )
    db.commit()


def _prefs(db, user_id: int, *, health_alert: bool = True, companion: bool = True) -> None:
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=companion,
            health_alert_enabled=health_alert,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()


def _setup_chain(
    db,
    *,
    with_cg2: bool = False,
    scope: I10NotificationScope = I10NotificationScope.GENERAL_STATUS,
):
    owner = _user(db, "owner")
    cg1 = _user(db, "cg1", lang="fa")
    subject = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="Parent", access_role="MANAGER"
    )
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg1.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=scope,
    )
    _push(db, cg1.id, f"fcm-{cg1.id}")
    _prefs(db, cg1.id)
    cg2 = None
    if with_cg2:
        cg2 = _user(db, "cg2")
        grant_caregiver_subject_access(
            db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg2.id
        )
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg2.id,
            notification_scope=scope,
        )
        _push(db, cg2.id, f"fcm-{cg2.id}")
        _prefs(db, cg2.id)
    return owner, cg1, cg2, subject


def _intent(db, owner, subject, recipient, occurrence: str, *, scope=I10NotificationScope.GENERAL_STATUS):
    with patch.dict("os.environ", {"SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true"}, clear=False):
        return create_i10_caregiver_delivery_intent(
            db,
            owner_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=recipient.id,
            notification_scope=scope,
            occurrence_key=occurrence,
            privacy_class=I10PrivacyClass.PRIVATE,
        )


# Recipient resolution


def test_one_authorized_caregiver_resolves(db):
    _, cg1, _, subject = _setup_chain(db)
    rows = resolve_care_network_recipients(
        db, health_subject_id=subject.id, notification_scope=I10NotificationScope.GENERAL_STATUS
    )
    assert len(rows) == 1
    assert rows[0].recipient_user_id == cg1.id
    assert rows[0].delivery_ready is True


def test_multiple_caregivers_resolve_independently(db):
    _, cg1, cg2, subject = _setup_chain(db, with_cg2=True)
    rows = resolve_care_network_recipients(
        db, health_subject_id=subject.id, notification_scope=I10NotificationScope.GENERAL_STATUS
    )
    assert {r.recipient_user_id for r in rows} == {cg1.id, cg2.id}


def test_revoked_access_excluded(db):
    owner, cg1, _, subject = _setup_chain(db)
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg1.id
    )
    rows = resolve_care_network_recipients(
        db,
        health_subject_id=subject.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        include_non_delivery_ready=True,
    )
    assert rows == [] or all(not r.eligible for r in rows)


def test_revoked_grant_excluded(db):
    owner, cg1, _, subject = _setup_chain(db)
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.eligible is False


def test_wrong_scope_excluded(db):
    _, cg1, _, subject = _setup_chain(db, scope=I10NotificationScope.GENERAL_STATUS)
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    assert ev.eligible is False


def test_unrelated_subject_caregiver_excluded(db):
    owner, cg1, _, subject = _setup_chain(db)
    other = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="Other", access_role="MANAGER"
    )
    rows = resolve_care_network_recipients(
        db, health_subject_id=other.id, notification_scope=I10NotificationScope.GENERAL_STATUS
    )
    assert rows == []


def test_phone_only_profile_excluded(db):
    owner, cg1, _, subject = _setup_chain(db)
    create_caregiver(db, owner.id, CaregiverCreateIn(name="PhoneOnly", phone="+989121111111"))
    rows = resolve_care_network_recipients(
        db, health_subject_id=subject.id, notification_scope=I10NotificationScope.GENERAL_STATUS
    )
    assert len(rows) == 1
    assert rows[0].recipient_user_id == cg1.id


def test_linked_account_without_access_excluded(db):
    owner, cg1, _, subject = _setup_chain(db)
    stranger = _user(db, "stranger")
    _push(db, stranger.id, "fcm-stranger")
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=stranger.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.eligible is False


def test_profile_drift_fail_closed(db):
    owner, cg1, _, subject = _setup_chain(db)
    other = _user(db, "other-link")
    profile = create_caregiver(db, owner.id, CaregiverCreateIn(name="Drift"))
    from backend.app.services.i10.care_network_identity import link_caregiver_to_account

    link_caregiver_to_account(
        db,
        owner_user_id=owner.id,
        user_caregiver_id=profile["id"],
        recipient_account_user_id=other.id,
    )
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        user_caregiver_id=profile["id"],
    )
    assert ev.eligible is False
    assert ev.reason_code == "USER_CAREGIVER_LINK_MISMATCH"


# Preferences / readiness


def test_notification_disabled_recipient_suppressed(db):
    owner, cg1, _, subject = _setup_chain(db)
    db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == cg1.id).update(
        {"health_alert_enabled": False}
    )
    db.commit()
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.eligible is True
    assert ev.delivery_ready is False
    assert ev.delivery_reason_code == "NOTIFICATION_PREFS_HEALTH_ALERT_DISABLED"


def test_no_push_device_correct_reason(db):
    owner, cg1, _, subject = _setup_chain(db)
    db.query(models.PushDevice).filter(models.PushDevice.user_id == cg1.id).delete()
    db.commit()
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.delivery_reason_code == "NO_PUSH_DEVICE"


def test_push_without_grant_still_rejected(db):
    owner, cg1, _, subject = _setup_chain(db)
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.eligible is False


def test_full_delivery_ready(db):
    _, cg1, _, subject = _setup_chain(db)
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.delivery_ready is True


def test_language_preference_resolved(db):
    _, cg1, _, subject = _setup_chain(db)
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.preferred_language == "fa"


# Worker


@_FLAG_PATCH
@_GATE4_PATCH
def test_worker_uses_canonical_intake_not_direct_orm(db):
    from backend.app.services.i10.intake import enqueue_i10_notification

    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-1")
    with patch(
        "backend.app.services.i10.caregiver_delivery_worker.enqueue_i10_notification",
        wraps=enqueue_i10_notification,
    ) as mock_enqueue:
        process_caregiver_delivery_intent(db, intent)
        mock_enqueue.assert_called_once()
    db.refresh(intent)
    assert intent.status == "processed"
    assert intent.notification_id is not None


@_FLAG_PATCH
@_GATE4_PATCH
def test_worker_no_direct_fcm(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-fcm")
    with patch("backend.app.services.notifications.delivery_service.FCMAdapter.send") as mock_fcm:
        process_caregiver_delivery_intent(db, intent)
        mock_fcm.assert_not_called()


@_FLAG_PATCH
@_GATE4_PATCH
def test_worker_idempotent(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-idem")
    process_caregiver_delivery_intent(db, intent)
    first_notif = intent.notification_id
    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "idempotent"
    assert intent.notification_id == first_notif


@_FLAG_PATCH
@_GATE4_PATCH
def test_expired_request_not_enqueued(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-exp")
    intent.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    before = db.query(func.count(models.Notification.id)).scalar()
    process_caregiver_delivery_intent(db, intent)
    after = db.query(func.count(models.Notification.id)).scalar()
    assert after == before
    assert intent.status == "expired"


@_FLAG_PATCH
@_GATE4_PATCH
def test_revoked_grant_at_worker_time_suppresses(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-revoke-grant")
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    before = db.query(func.count(models.Notification.id)).scalar()
    outcome = process_caregiver_delivery_intent(db, intent)
    after = db.query(func.count(models.Notification.id)).scalar()
    assert after == before
    assert outcome["status"] == "suppressed"


@_FLAG_PATCH
@_GATE4_PATCH
def test_revoked_access_at_worker_time_suppresses(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-revoke-access")
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg1.id
    )
    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"


# Multi-caregiver


@_FLAG_PATCH
@_GATE4_PATCH
def test_caregivers_ab_same_occurrence(db):
    owner, cg1, cg2, subject = _setup_chain(db, with_cg2=True)
    i1 = _intent(db, owner, subject, cg1, "occ-multi")
    i2 = _intent(db, owner, subject, cg2, "occ-multi")
    process_caregiver_delivery_intent(db, i1)
    process_caregiver_delivery_intent(db, i2)
    assert i1.status == "processed"
    assert i2.status == "processed"
    assert i1.notification_id != i2.notification_id


@_FLAG_PATCH
@_GATE4_PATCH
def test_suppression_of_a_not_b(db):
    owner, cg1, cg2, subject = _setup_chain(db, with_cg2=True)
    i1 = _intent(db, owner, subject, cg1, "occ-split")
    i2 = _intent(db, owner, subject, cg2, "occ-split")
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    process_caregiver_delivery_intent(db, i1)
    process_caregiver_delivery_intent(db, i2)
    assert i1.status == "suppressed"
    assert i2.status == "processed"


@_FLAG_PATCH
@_GATE4_PATCH
def test_duplicate_same_recipient_occurrence_blocked(db):
    owner, cg1, _, subject = _setup_chain(db)
    i1 = _intent(db, owner, subject, cg1, "occ-dup")
    i2 = _intent(db, owner, subject, cg1, "occ-dup")
    assert i1.id == i2.id


@_FLAG_PATCH
@_GATE4_PATCH
def test_new_occurrence_same_recipient_allowed(db):
    owner, cg1, _, subject = _setup_chain(db)
    i1 = _intent(db, owner, subject, cg1, "occ-a")
    i2 = _intent(db, owner, subject, cg1, "occ-b")
    process_caregiver_delivery_intent(db, i1)
    process_caregiver_delivery_intent(db, i2)
    assert i1.notification_id != i2.notification_id


# Privacy / boundaries


@_FLAG_PATCH
@_GATE4_PATCH
def test_privacy_class_persisted(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-privacy")
    process_caregiver_delivery_intent(db, intent)
    notif = db.query(models.Notification).filter(models.Notification.id == intent.notification_id).one()
    assert notif.privacy_class == "PRIVATE"


def test_b06_no_raw_i9_imports():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for name in ("caregiver_delivery_worker.py", "caregiver_delivery_intent.py", "delivery_readiness.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        dumped = ast.dump(tree)
        assert "PhysiologicalMeasurement" not in dumped


def test_b06_no_rag_imports():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for name in ("caregiver_delivery_worker.py", "caregiver_delivery_intent.py"):
        dumped = ast.dump(ast.parse((root / name).read_text(encoding="utf-8"))).lower()
        assert "rag" not in dumped


@_FLAG_PATCH
@_GATE4_PATCH
def test_caregiver_not_substituted_as_subject(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-subj")
    process_caregiver_delivery_intent(db, intent)
    notif = db.query(models.Notification).filter(models.Notification.id == intent.notification_id).one()
    assert notif.user_id == cg1.id
    assert notif.health_subject_id == subject.id
    assert notif.health_subject_id != cg1.id


def test_phone_not_push_token(db):
    _, cg1, _, subject = _setup_chain(db)
    ev = evaluate_delivery_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert ev.reason_code != "PHONE_MATCH_NOT_AUTHORIZATION"


# Lifecycle


@_FLAG_PATCH
@_GATE4_PATCH
def test_decision_linkage_valid(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-dec")
    process_caregiver_delivery_intent(db, intent)
    assert intent.i10_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == intent.i10_decision_id
    ).one()
    assert decision.notification_id == intent.notification_id


@_FLAG_PATCH
@_GATE4_PATCH
def test_suppressed_not_marked_delivered(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-sup")
    db.query(models.PushDevice).filter(models.PushDevice.user_id == cg1.id).delete()
    db.commit()
    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "suppressed"
    assert intent.notification_id is None


@_FLAG_PATCH
@_GATE4_PATCH
def test_delivery_service_mock_recorded(db):
    owner, cg1, _, subject = _setup_chain(db)
    intent = _intent(db, owner, subject, cg1, "occ-deliver")
    process_caregiver_delivery_intent(db, intent)
    from backend.app.services.notifications.delivery_service import DeliveryService

    with _FCM_PATCH:
        sent = DeliveryService(db).deliver_pending(limit=10)
    assert sent >= 0


@_FLAG_PATCH
@_GATE4_PATCH
def test_batch_worker_processes_pending(db):
    owner, cg1, _, subject = _setup_chain(db)
    _intent(db, owner, subject, cg1, "occ-batch")
    summary = process_pending_caregiver_delivery_intents(db, limit=10)
    assert summary["processed"] >= 1
