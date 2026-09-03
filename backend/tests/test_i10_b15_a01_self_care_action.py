"""I10-B15-A01 — SELF HealthSubject CARE_ACTION eligibility (PostgreSQL)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.app import models
from backend.app.services.i10.care_action_producer_worker import (
    list_eligible_managed_care_actions,
    run_care_action_producer_for_subject,
    run_care_action_producer_scan,
)
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access, revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import create_subject_notification_grant, revoke_subject_notification_grant_by_scope
from backend.app.services.i10.managed_i8_action_binding import (
    build_health_subject_context_refs_json,
    is_managed_health_subject,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
    },
    clear=False,
)


@pytest.fixture
def a01_patches():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{uuid4().hex[:6]}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _push_prefs(db, user_id: int) -> None:
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=f"fcm-{user_id}", is_active=True))
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
    return datetime(2026, 9, 3, 14, 0, 0, tzinfo=timezone.utc)


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


def _setup_self(db, *, daughter_care_action: bool = True, stranger_access: bool = False):
    patient = _user(db, "patient")
    spouse = _user(db, "spouse")
    daughter = _user(db, "daughter")
    stranger = _user(db, "stranger")
    subject = ensure_self_subject_for_account(db, patient.id, display_name="SelfPatient", commit=True)
    assert subject.linked_user_id == patient.id
    assert is_managed_health_subject(db, subject.id) is False
    for cg in (spouse, daughter):
        grant_caregiver_subject_access(
            db, actor_user_id=patient.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
        )
        _push_prefs(db, cg.id)
        create_subject_notification_grant(
            db,
            actor_user_id=patient.id,
            health_subject_id=subject.id,
            recipient_user_id=cg.id,
            notification_scope=I10NotificationScope.CARE_ACTION,
        )
    if not daughter_care_action:
        revoke_subject_notification_grant_by_scope(
            db,
            actor_user_id=patient.id,
            health_subject_id=subject.id,
            recipient_user_id=daughter.id,
            notification_scope=I10NotificationScope.CARE_ACTION,
        )
        create_subject_notification_grant(
            db,
            actor_user_id=patient.id,
            health_subject_id=subject.id,
            recipient_user_id=daughter.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    if stranger_access:
        grant_caregiver_subject_access(
            db, actor_user_id=patient.id, health_subject_id=subject.id, recipient_account_user_id=stranger.id
        )
        _push_prefs(db, stranger.id)
    return patient, spouse, daughter, stranger, subject


def _action(db, owner, subject, when, *, key: str = "self-act-1", refs=None, domain: str = "routine", status: str = "ACTIVE"):
    _profile_tz(db, owner.id)
    window = resolve_local_day_window(db, owner.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=owner.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{subject.id}-{key}-{owner.id}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=owner.id,
        plan_id=plan.id,
        action_domain=domain,
        action_type=f"{domain}_care_item",
        action_idempotency_key=key,
        summary_text="SELF governed routine check",
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json=refs if refs is not None else build_health_subject_context_refs_json(subject.id),
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    if status != "ACTIVE":
        action.status = status
    db.commit()
    return action


def test_self_subject_care_action_delivers_to_granted_caregivers(db, a01_patches):
    patient, spouse, daughter, stranger, subject = _setup_self(db)
    when = _when()
    _action(db, patient, subject, when)
    outcome = run_care_action_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=True, commit=True
    )
    assert outcome["intents"] == 2
    assert (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == spouse.id,
            models.Notification.semantic_family == I10SemanticFamily.CARE_ACTION.value,
            models.Notification.health_subject_id == subject.id,
        )
        .count()
        == 1
    )
    assert (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == daughter.id,
            models.Notification.semantic_family == I10SemanticFamily.CARE_ACTION.value,
            models.Notification.health_subject_id == subject.id,
        )
        .count()
        == 1
    )
    assert db.query(models.Notification).filter(models.Notification.user_id == stranger.id).count() == 0
    notif = db.query(models.Notification).filter(models.Notification.user_id == spouse.id).one()
    assert notif.user_id != subject.id
    assert notif.health_subject_id == subject.id


def test_managed_path_still_works(db, a01_patches):
    owner = _user(db, "mgr")
    cg = _user(db, "cg-m")
    subject = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="Unlinked", access_role="MANAGER"
    )
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    _push_prefs(db, cg.id)
    when = _when()
    _action(db, owner, subject, when, key="managed-keep")
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg.id).count() == 1


def test_no_context_ref_no_care_action(db, a01_patches):
    patient, _, _, _, subject = _setup_self(db)
    when = _when()
    _action(db, patient, subject, when, refs="[]")
    outcome = run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert outcome["actions"] == 0
    assert outcome["intents"] == 0


def test_wrong_subject_context_ref_denied(db, a01_patches):
    patient, spouse, _, _, subject = _setup_self(db)
    other = create_managed_subject_without_account(
        db, account_user_id=patient.id, display_name="OtherHuman", access_role="MANAGER"
    )
    when = _when()
    _action(db, patient, other, when, key="wrong-hs")
    outcome = run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert outcome["intents"] == 0
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 0


def test_unrelated_account_plan_denied(db, a01_patches):
    patient, spouse, _, stranger, subject = _setup_self(db)
    when = _when()
    _profile_tz(db, stranger.id)
    _action(db, stranger, subject, when, key="stolen")
    outcome = run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert outcome["intents"] == 0
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 0


def test_general_grant_only_denied(db, a01_patches):
    patient, spouse, daughter, _, subject = _setup_self(db, daughter_care_action=False)
    when = _when()
    _action(db, patient, subject, when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == daughter.id).count() == 0


def test_access_without_care_action_grant_denied(db, a01_patches):
    patient, spouse, _, stranger, subject = _setup_self(db, stranger_access=True)
    when = _when()
    _action(db, patient, subject, when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert db.query(models.Notification).filter(models.Notification.user_id == stranger.id).count() == 0
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 1


def test_revoked_access_no_intent(db, a01_patches):
    patient, spouse, _, _, subject = _setup_self(db)
    revoke_caregiver_subject_access(
        db, actor_user_id=patient.id, health_subject_id=subject.id, recipient_account_user_id=spouse.id
    )
    when = _when()
    _action(db, patient, subject, when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 0


def test_inactive_subject_denied(db, a01_patches):
    patient, _, _, _, subject = _setup_self(db)
    when = _when()
    _action(db, patient, subject, when)
    subject.status = "inactive"
    db.commit()
    eligible = list_eligible_managed_care_actions(db, health_subject_id=subject.id, now=when)
    assert eligible == []
    outcome = run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert outcome["actions"] == 0


def test_expired_action_denied(db, a01_patches):
    patient, spouse, _, _, subject = _setup_self(db)
    when = _when()
    action = _action(db, patient, subject, when)
    action.expires_at = when - timedelta(hours=1)
    db.commit()
    outcome = run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert outcome["actions"] == 0
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 0


def test_inactive_action_denied(db, a01_patches):
    patient, spouse, _, _, subject = _setup_self(db)
    when = _when()
    _action(db, patient, subject, when, status="CANCELLED")
    outcome = run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert outcome["actions"] == 0
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 0


def test_raw_i9_and_rag_do_not_mint(db, a01_patches):
    patient, spouse, _, _, subject = _setup_self(db)
    when = _when()
    db.add(
        models.PhysiologicalMeasurementRollup(
            user_id=patient.id,
            health_subject_id=subject.id,
            measurement_type="heart_rate",
            bucket_kind="daily",
            bucket_start=datetime(when.year, when.month, when.day, tzinfo=timezone.utc),
            bucket_end=when - timedelta(hours=2),
            sample_count=10,
            avg_value=70.0,
            coverage=0.8,
        )
    )
    db.commit()
    retrieve_knowledge_context(db, "ALS care", language="en", limit=3)
    outcome = run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert outcome["intents"] == 0
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 0


def test_duplicate_producer_idempotent(db, a01_patches):
    patient, spouse, _, _, subject = _setup_self(db)
    when = _when()
    _action(db, patient, subject, when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == spouse.id,
            models.Notification.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
        == 1
    )


def test_scan_includes_self_subject_with_caregiver(db, a01_patches):
    patient, spouse, _, _, subject = _setup_self(db)
    when = _when()
    _action(db, patient, subject, when, key="scan-self")
    summary = run_care_action_producer_scan(db, now=when, deliver=True)
    assert summary["processed"] >= 1
    assert db.query(models.Notification).filter(models.Notification.user_id == spouse.id).count() == 1
