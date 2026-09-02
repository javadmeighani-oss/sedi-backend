"""I10-B18 canonical interruption policy (PostgreSQL + FastAPI cross-section)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.gate4.notification_contract import SmartNotificationRisk
from backend.app.services.i10.b14_overlap_policy import B14_OVERLAP_REASON_STATUS_REDUNDANT
from backend.app.services.i10.canonical_policy import (
    I10_CANONICAL_POLICY_VERSION,
    evaluate_i10_canonical_policy,
    resolve_i10_policy_risk,
)
from backend.app.services.i10.care_digest_producer_worker import run_care_digest_producer_for_subject
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access
from backend.app.services.i10.care_network_grants import create_subject_notification_grant
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.managed_i8_action_binding import build_health_subject_context_refs_json
from backend.app.services.i10.policy_types import I10DecisionValue, I10NotificationScope, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
        "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
        "SEDI_GATE4_FEEDBACK_POLICY": "true",
        "SEDI_GATE4_ACTIVE_CONVERSATION_DEFER": "true",
    },
    clear=False,
)
_BRAIN_PATCH = patch(
    "backend.app.core.conversation.brain.ConversationBrain.process_message",
    return_value={"message": "Ok", "language": "en"},
)
_CMD_PATCH = patch(
    "backend.app.services.chat_commands.detect_and_handle_user_settings_command",
    return_value=None,
)


@pytest.fixture
def b18_env():
    with _FLAG_PATCH, _BRAIN_PATCH, _CMD_PATCH:
        yield


@pytest.fixture()
def client(db):
    def _get_db_override():
        yield db

    sedi_app.dependency_overrides[_app_get_db] = _get_db_override
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _auth(user: models.User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user.id})}"}


def _feedback(client, user: models.User, notification_id: int, payload: dict):
    return client.post(
        f"/notifications/{notification_id}/feedback",
        json=payload,
        headers=_auth(user),
    )


def _candidate(**kwargs) -> I10NotificationCandidate:
    defaults = dict(
        candidate_key="i10:test:candidate:1",
        health_subject_id=1,
        recipient_user_id=1,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        source_owner="TEST",
        source_type="test",
        source_id="1",
        semantic_family=I10SemanticFamily.GENERAL_STATUS,
    )
    defaults.update(kwargs)
    return I10NotificationCandidate(**defaults)


def test_normal_allow_policy(db, b18_env):
    user = _user(db, "self-allow")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=user.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        semantic_family=I10SemanticFamily.GENERAL_STATUS,
    )
    outcome = evaluate_i10_canonical_policy(db, candidate=cand, payload_metadata={"priority": "normal"})
    assert outcome.decision == I10DecisionValue.SEND
    assert outcome.reason_code == "POLICY_ALLOW"


def test_user_pref_suppresses(db, b18_env):
    user = _user(db, "pref-off")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    db.add(
        models.NotificationPrefs(
            user_id=user.id,
            companion_enabled=True,
            health_alert_enabled=False,
            reminder_system_enabled=True,
        )
    )
    db.commit()
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=user.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    outcome = evaluate_i10_canonical_policy(db, candidate=cand)
    assert outcome.decision == I10DecisionValue.SUPPRESS
    assert "PREFS" in outcome.reason_code


def test_quiet_hours_defer(db, b18_env):
    user = _user(db, "quiet-user")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    db.add(
        models.NotificationPrefs(
            user_id=user.id,
            quiet_hours_enabled=True,
            quiet_start="22:00",
            quiet_end="08:00",
            companion_enabled=True,
            health_alert_enabled=True,
        )
    )
    db.add(models.UserProfileCore(user_id=user.id, timezone="Asia/Tehran"))
    db.commit()
    now_utc = datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc)
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=user.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    outcome = evaluate_i10_canonical_policy(db, candidate=cand, now_utc=now_utc)
    assert outcome.decision == I10DecisionValue.DEFER
    assert outcome.reason_code == "QUIET_HOURS_DEFER"
    assert outcome.defer_until is not None


def test_active_conversation_defer(db, b18_env):
    user = _user(db, "chat-active")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    db.add(
        models.NotificationPrefs(
            user_id=user.id,
            companion_enabled=True,
            health_alert_enabled=True,
        )
    )
    now = datetime.now(timezone.utc)
    db.add(
        models.InteractionEvent(
            user_id=user.id,
            event_type="chat_message",
            source="chat",
            interaction_channel="text",
            created_at=now.replace(tzinfo=None),
        )
    )
    db.commit()
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=user.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    outcome = evaluate_i10_canonical_policy(db, candidate=cand, now_utc=now)
    assert outcome.decision == I10DecisionValue.DEFER
    assert outcome.reason_code == "ACTIVE_CONVERSATION_DEFER"


def test_not_now_suppresses_later_candidate(db, b18_env, client):
    user = _user(db, "not-now-user")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    db.add(
        models.NotificationPrefs(
            user_id=user.id,
            companion_enabled=True,
            health_alert_enabled=True,
        )
    )
    notif = models.Notification(
        user_id=user.id,
        type="companion_ping",
        title="Hi",
        body="Check in",
        priority="normal",
        channel="companion",
        category="companion",
        template_key="companion_ping",
        health_subject_id=subject.id,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    r = _feedback(client, user, notif.id, {"reaction": "interact", "action_id": "NOT_NOW"})
    assert r.status_code == 200
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=user.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    outcome = evaluate_i10_canonical_policy(
        db,
        candidate=cand,
        payload_metadata={"template_key": "companion_ping", "category": "companion"},
        notification_type="companion_ping",
    )
    assert outcome.decision == I10DecisionValue.SUPPRESS
    assert "FEEDBACK" in outcome.reason_code


def test_critical_safety_bypasses_quiet_hours(db, b18_env):
    cg = _user(db, "safety-cg")
    owner = _user(db, "safety-owner")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    db.add(
        models.NotificationPrefs(
            user_id=cg.id,
            quiet_hours_enabled=True,
            quiet_start="00:00",
            quiet_end="23:59",
            health_alert_enabled=True,
            companion_enabled=True,
        )
    )
    db.commit()
    now_utc = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
        semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
        candidate_key="i10:safety:1",
    )
    assert resolve_i10_policy_risk(cand, {}) == SmartNotificationRisk.CRITICAL.value
    outcome = evaluate_i10_canonical_policy(db, candidate=cand, now_utc=now_utc)
    assert outcome.decision == I10DecisionValue.SEND
    assert outcome.reason_code == "CRITICAL_ALLOWED"


def test_critical_pref_off_still_suppressed(db, b18_env):
    cg = _user(db, "safety-pref-off")
    owner = _user(db, "owner2")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    db.add(
        models.NotificationPrefs(
            user_id=cg.id,
            health_alert_enabled=False,
            companion_enabled=True,
        )
    )
    db.commit()
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
        semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
        candidate_key="i10:safety:2",
    )
    outcome = evaluate_i10_canonical_policy(db, candidate=cand)
    assert outcome.decision == I10DecisionValue.SUPPRESS
    assert "PREFS" in outcome.reason_code


def test_recipient_isolation_not_now(db, b18_env, client):
    owner = _user(db, "iso-owner")
    cg_a = _user(db, "iso-a")
    cg_b = _user(db, "iso-b")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    for cg in (cg_a, cg_b):
        grant_caregiver_subject_access(
            db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
        )
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
        db.add(
            models.NotificationPrefs(
                user_id=cg.id,
                companion_enabled=True,
                health_alert_enabled=True,
            )
        )
    notif = models.Notification(
        user_id=cg_a.id,
        type="companion_ping",
        title="Hi",
        body="Body",
        channel="companion",
        category="companion",
        template_key="companion_ping",
        health_subject_id=subject.id,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    _feedback(client, cg_a, notif.id, {"reaction": "interact", "action_id": "NOT_NOW"})
    cand_a = _candidate(
        candidate_key="i10:iso:a",
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    cand_b = _candidate(
        candidate_key="i10:iso:b",
        health_subject_id=subject.id,
        recipient_user_id=cg_b.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    meta = {"template_key": "companion_ping", "category": "companion"}
    assert (
        evaluate_i10_canonical_policy(
            db, candidate=cand_a, payload_metadata=meta, notification_type="companion_ping"
        ).decision
        == I10DecisionValue.SUPPRESS
    )
    assert (
        evaluate_i10_canonical_policy(
            db, candidate=cand_b, payload_metadata=meta, notification_type="companion_ping"
        ).decision
        == I10DecisionValue.SEND
    )


def test_b14_overlap_suppresses_redundant_status(db, b18_env):
    owner = _user(db, "b14-owner")
    cg = _user(db, "b14-cg")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    for scope in (I10NotificationScope.GENERAL_STATUS, I10NotificationScope.DEVICE_STATUS):
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg.id,
            notification_scope=scope,
        )
    db.add(models.PushDevice(user_id=cg.id, platform="android", fcm_token="fcm-b14", is_active=True))
    db.add(
        models.NotificationPrefs(
            user_id=cg.id,
            companion_enabled=True,
            health_alert_enabled=True,
        )
    )
    db.commit()
    when = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
    start = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)
    db.add(
        models.PhysiologicalMeasurementRollup(
            user_id=owner.id,
            health_subject_id=subject.id,
            measurement_type="heart_rate",
            bucket_kind="daily",
            bucket_start=start,
            bucket_end=when - timedelta(hours=60),
            sample_count=10,
            avg_value=78.0,
            coverage=0.9,
        )
    )
    db.commit()
    outcome = run_care_digest_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=True, commit=True
    )
    assert outcome["gap_intents"] >= 1
    status_notifs = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == cg.id,
            models.Notification.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .count()
    )
    gap_notifs = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == cg.id,
            models.Notification.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .count()
    )
    assert gap_notifs == 1
    assert status_notifs == 0
    suppressed = (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.reason_code == B14_OVERLAP_REASON_STATUS_REDUNDANT)
        .count()
    )
    assert suppressed >= 1


def test_care_action_not_mutated_by_policy_suppress(db, b18_env):
    owner = _user(db, "ca-owner")
    cg = _user(db, "ca-cg")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
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
    db.add(models.PushDevice(user_id=cg.id, platform="android", fcm_token="fcm-ca", is_active=True))
    db.add(
        models.NotificationPrefs(
            user_id=cg.id,
            companion_enabled=True,
            health_alert_enabled=True,
            reminder_system_enabled=True,
        )
    )
    when = datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc)
    window = resolve_local_day_window(db, owner.id, now_utc=when)
    repo = I8OperationalRepository(db)
    plan = repo.create_plan(user_id=owner.id, health_subject_id=subject.id, plan_type="routine", status="ACTIVE")
    action = repo.create_action(
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_care_item",
        action_idempotency_key="b18-care",
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
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True, commit=True)
    db.refresh(action)
    assert action.status == "ACTIVE"


def test_vocabulary_constants():
    assert I10_CANONICAL_POLICY_VERSION == "i10.b18.1"
