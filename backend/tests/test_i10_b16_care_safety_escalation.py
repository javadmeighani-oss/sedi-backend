"""I10-B16 CARE_SAFETY_ESCALATION — authoritative I4/Section-10 escalation → Care Network (PostgreSQL)."""

from __future__ import annotations

import ast
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.app import models
from backend.app.schemas.chat import ChatRequest
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.care_digest_producer_worker import run_care_digest_producer_for_subject
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access, revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import create_subject_notification_grant, revoke_subject_notification_grant_by_scope
from backend.app.services.i10.care_safety_producer_worker import (
    bind_escalation_health_subject_metadata,
    run_care_safety_producer_for_subject,
)
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.i4_escalation_authority import AUTHORITATIVE_ESCALATION_STATE
from backend.app.services.i10.managed_i8_action_binding import build_health_subject_context_refs_json
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account
from backend.app.services.section10.emergency_escalation_service import (
    create_escalation_record,
    transition_escalation_state,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
        "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
    },
    clear=False,
)


@pytest.fixture
def b16_patches():
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


def _prefs(db, user_id: int, *, reminder_system: bool = True) -> None:
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=True,
            health_alert_enabled=True,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=reminder_system,
        )
    )
    db.commit()


def _when() -> datetime:
    return datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)


def _rollup(db, owner, subject, when):
    start = datetime(when.year, when.month, when.day, tzinfo=timezone.utc)
    db.add(
        models.PhysiologicalMeasurementRollup(
            user_id=owner.id,
            health_subject_id=subject.id,
            measurement_type="heart_rate",
            bucket_kind="daily",
            bucket_start=start,
            bucket_end=when - timedelta(hours=2),
            sample_count=10,
            avg_value=78.0,
            coverage=0.8,
        )
    )
    db.commit()


def _authoritative_escalation(
    db,
    owner: models.User,
    subject: models.HealthSubject,
    *,
    reason: str = "no_ack",
    state: str = AUTHORITATIVE_ESCALATION_STATE,
) -> models.EmergencyEscalationRecord:
    rec = create_escalation_record(db, owner.id, reason)
    rec = bind_escalation_health_subject_metadata(db, rec, health_subject_id=subject.id)
    if state != "monitoring":
        rec = transition_escalation_state(db, rec, state)
    return rec


def _setup_caregivers(
    db,
    *,
    cg_a_safety: bool = True,
    cg_b_safety: bool = False,
    cg_b_general: bool = False,
    cg_a_sensitive: bool = False,
):
    owner = _user(db, "owner")
    cg_a = _user(db, "cg-a")
    cg_b = _user(db, "cg-b")
    subject = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="Parent", access_role="MANAGER"
    )
    assert subject.linked_user_id is None
    for cg in (cg_a, cg_b):
        grant_caregiver_subject_access(
            db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
        )
        _push(db, cg.id, f"fcm-{cg.id}")
        _prefs(db, cg.id)
    if cg_a_safety:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_a.id,
            notification_scope=I10NotificationScope.SAFETY_ESCALATION,
        )
    if cg_b_safety:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_b.id,
            notification_scope=I10NotificationScope.SAFETY_ESCALATION,
        )
    if cg_b_general:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_b.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    if cg_a_sensitive:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_a.id,
            notification_scope=I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
        )
    return owner, cg_a, cg_b, subject


def _run_pipeline(db, subject, *, deliver: bool = True) -> dict:
    return run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=deliver, commit=True)


def _managed_action(db, owner, subject, when):
    _profile_tz(db, owner.id)
    window = resolve_local_day_window(db, owner.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=owner.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{subject.id}-b16",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=owner.id,
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_care_item",
        action_idempotency_key="b16-act",
        summary_text="Evening check",
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json=build_health_subject_context_refs_json(subject.id),
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    return action


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


# A authoritative safety


def test_authoritative_escalation_real_path(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    esc = _authoritative_escalation(db, owner, subject)
    assert esc.current_state == AUTHORITATIVE_ESCALATION_STATE
    _run_pipeline(db, subject)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg_a.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        )
        .one()
    )
    assert intent.status == "processed"
    notif = db.query(models.Notification).filter(models.Notification.id == intent.notification_id).one()
    assert notif.user_id == cg_a.id
    assert notif.health_subject_id == subject.id
    assert notif.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value
    assert intent.i10_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(models.I10NotificationDecision.id == intent.i10_decision_id).one()
    assert decision.decision == "SEND"


def test_caregiver_not_substituted_as_subject(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    assert notif.health_subject_id == subject.id
    assert notif.user_id != subject.id


# B non-escalation


def test_non_escalated_state_no_notification(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject, state="monitoring")
    outcome = _run_pipeline(db, subject)
    assert outcome["intents"] == 0


def test_resolved_escalation_no_notification(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    rec = _authoritative_escalation(db, owner, subject)
    transition_escalation_state(db, rec, "resolved", resolution_source="test")
    outcome = _run_pipeline(db, subject)
    assert outcome["intents"] == 0


# C false escalation prevention


def test_no_data_only_no_care_safety(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value)
        .count()
        == 0
    )


def test_stale_data_only_no_care_safety(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert (
        db.query(models.Notification)
        .filter(models.Notification.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value)
        .count()
        == 0
    )


def test_care_data_gap_only_no_care_safety(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    start = datetime(when.year, when.month, when.day, tzinfo=timezone.utc)
    db.add(
        models.PhysiologicalBaseline(
            user_id=owner.id,
            health_subject_id=subject.id,
            measurement_type="heart_rate",
            baseline_method="PERSONAL_OBSERVED_BASELINE_V1",
            baseline_value=70.0,
            window_start=start - timedelta(days=7),
            window_end=start,
            derived_at=when - timedelta(days=3),
            coverage=0.8,
            valid_day_count=10,
        )
    )
    db.commit()
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert (
        db.query(models.Notification)
        .filter(models.Notification.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value)
        .count()
        == 0
    )


def test_care_status_only_no_care_safety(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert (
        db.query(models.Notification)
        .filter(models.Notification.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value)
        .count()
        == 0
    )


def test_care_action_only_no_care_safety(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert (
        db.query(models.Notification)
        .filter(models.Notification.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value)
        .count()
        == 0
    )


def test_generic_alert_without_escalation_no_care_safety(db, b16_patches):
    owner, _, _, subject = _setup_caregivers(db)
    db.add(
        models.CareRiskAssessment(
            user_id=owner.id,
            risk_level="emergency",
            reasons_json='["high_risk_medical_keywords"]',
            message_hash="abc123",
            source="api",
        )
    )
    db.commit()
    outcome = _run_pipeline(db, subject)
    assert outcome["intents"] == 0


# D scope matrix


@pytest.mark.parametrize(
    "scope,should_notify",
    [
        (I10NotificationScope.SAFETY_ESCALATION, True),
        (I10NotificationScope.GENERAL_STATUS, False),
        (I10NotificationScope.DEVICE_STATUS, False),
        (I10NotificationScope.CARE_ACTION, False),
        (I10NotificationScope.SENSITIVE_HEALTH_DETAIL, False),
    ],
)
def test_scope_matrix(db, b16_patches, scope, should_notify):
    owner = _user(db, "owner-scope")
    cg = _user(db, "cg-scope")
    subject = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="ScopeParent", access_role="MANAGER"
    )
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=scope,
    )
    _push(db, cg.id, "fcm-scope")
    _prefs(db, cg.id)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    count = db.query(models.Notification).filter(models.Notification.user_id == cg.id).count()
    assert (count == 1) if should_notify else (count == 0)


# E privacy


def test_minimal_alert_without_sensitive_grant(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db, cg_a_sensitive=False)
    _authoritative_escalation(db, owner, subject, reason="no_ack")
    _run_pipeline(db, subject)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    body = (notif.body or "").lower()
    assert "governed safety escalation" in body
    assert "78" not in body
    assert "bpm" not in body


def test_bounded_detail_with_sensitive_grant(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db, cg_a_sensitive=True)
    _authoritative_escalation(db, owner, subject, reason="no_ack")
    _run_pipeline(db, subject)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    assert "no_ack" in (notif.body or "")


def test_protected_clinical_values_absent(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    meta = {"health_subject_id": subject.id, "raw_hr": 180, "sample_value": 99.9}
    rec = create_escalation_record(db, owner.id, "no_ack")
    rec.metadata_json = json.dumps(meta)
    db.commit()
    rec = transition_escalation_state(db, rec, AUTHORITATIVE_ESCALATION_STATE)
    _run_pipeline(db, subject)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    body = notif.body or ""
    assert "180" not in body
    assert "99.9" not in body


# F access / grant revoke


def test_revoke_access_before_delivery(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intent = db.query(models.CaregiverNotificationIntent).filter(models.CaregiverNotificationIntent.recipient_user_id == cg_a.id).one()
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg_a.id
    )
    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "suppressed"


def test_revoke_safety_grant_before_delivery(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intent = db.query(models.CaregiverNotificationIntent).filter(models.CaregiverNotificationIntent.recipient_user_id == cg_a.id).one()
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "suppressed"


def test_unrelated_grant_still_suppressed(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 0


# G prefs


def test_pref_on_delivers(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1


def test_pref_off_suppressed(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == cg_a.id).update(
        {"reminder_system_enabled": False}
    )
    db.commit()
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intent = db.query(models.CaregiverNotificationIntent).one()
    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "suppressed"


# H multi caregiver


def test_multi_caregiver_independent(db, b16_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_safety=True)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_b.id).count() == 1


def test_revoke_a_not_b(db, b16_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_safety=True)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intents = db.query(models.CaregiverNotificationIntent).all()
    i_a = next(i for i in intents if i.recipient_user_id == cg_a.id)
    i_b = next(i for i in intents if i.recipient_user_id == cg_b.id)
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg_a.id
    )
    process_caregiver_delivery_intent(db, i_a)
    process_caregiver_delivery_intent(db, i_b)
    assert i_a.status == "suppressed"
    assert i_b.status == "processed"


def test_general_only_b_denied(db, b16_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_general=True)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_b.id).count() == 0


# I idempotency


def test_same_occurrence_same_recipient_once(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    _run_pipeline(db, subject)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1


def test_same_occurrence_different_recipient_allowed(db, b16_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_safety=True)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    assert db.query(models.Notification).count() == 2


def test_new_occurrence_allowed(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject, reason="no_ack")
    _authoritative_escalation(db, owner, subject, reason="inactivity")
    _run_pipeline(db, subject)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 2


# J chat


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_real_chat_continuation(mock_cmd, mock_reminder, mock_brain, db, b16_patches, monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_brain.return_value = {"message": "Ok", "language": "en"}
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    from backend.app.routers.interact import chat
    from starlette.requests import Request

    payload = ChatRequest(message="about safety", source_notification_id=notif.id, conversation_id="b16-conv")
    scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
    resp = asyncio.run(chat(Request(scope), payload, db, cg_a))
    assert resp.continued_from_notification is True
    assert notif.health_subject_id == subject.id


def test_revoked_chat_fail_closed(db, b16_patches):
    from backend.app.services.gate4.notification_chat_context import build_safe_chat_context

    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    ctx = build_safe_chat_context(notif, db=db, viewer_user_id=cg_a.id)
    assert ctx.get("subject_context_available") == "false"


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_cross_user_denied(mock_cmd, mock_reminder, mock_brain, db, b16_patches, monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    owner, cg_a, other, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    _run_pipeline(db, subject)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    from backend.app.routers.interact import chat
    from starlette.requests import Request

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            chat(
                Request({"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}),
                ChatRequest(message="hi", source_notification_id=notif.id),
                db,
                other,
            )
        )
    assert exc.value.status_code == 403


# M transaction failure


def test_enqueue_failure_not_processed(db, b16_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intent = db.query(models.CaregiverNotificationIntent).filter(models.CaregiverNotificationIntent.recipient_user_id == cg_a.id).one()
    calls = {"n": 0}

    def _fail_once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bounded_failure")
        from backend.app.services.i10.intake import enqueue_i10_notification as real

        return real(*args, **kwargs)

    with patch("backend.app.services.i10.caregiver_delivery_worker.enqueue_i10_notification", side_effect=_fail_once):
        with pytest.raises(RuntimeError):
            process_caregiver_delivery_intent(db, intent)
    assert intent.status == "pending"
    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "processed"


# boundaries


def test_b16_no_direct_notification_orm():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for name in ("care_safety_producer_worker.py", "care_safety_copy.py", "i4_escalation_authority.py"):
        dumped = ast.dump(ast.parse((root / name).read_text(encoding="utf-8")))
        assert "Notification(" not in dumped


def test_b16_no_raw_i9():
    text = (Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "care_safety_producer_worker.py").read_text()
    assert "PhysiologicalMeasurement" not in text


def test_b16_no_rag():
    text = (Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "care_safety_producer_worker.py").read_text().lower()
    assert "rag_service" not in text


def test_no_escalation_no_producer(db, b16_patches):
    _, _, _, subject = _setup_caregivers(db)
    outcome = _run_pipeline(db, subject)
    assert outcome["escalations"] == 0
    assert outcome["intents"] == 0
