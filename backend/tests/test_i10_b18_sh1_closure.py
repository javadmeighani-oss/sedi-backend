"""I10-B18-SH1 — canonical policy contract closure (PostgreSQL + FastAPI)."""

from __future__ import annotations

import json
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
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_contract import (
    NOT_NOW_SUPPRESS_HOURS,
    SmartNotificationRisk,
)
from backend.app.services.i10.b14_overlap_policy import (
    B14_OVERLAP_REASON_KEEP_BOTH,
    B14_OVERLAP_REASON_STATUS_REDUNDANT,
    evaluate_b14_overlap,
)
from backend.app.services.i10.care_network_access import (
    grant_caregiver_subject_access,
    revoke_caregiver_subject_access,
)
from backend.app.services.i10.care_network_grants import (
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.care_safety_copy import (
    CARE_SAFETY_INTERRUPTION_POLICY_RISK,
    CARE_SAFETY_POLICY_RISK_SOURCE,
)
from backend.app.services.i10.care_safety_producer_worker import (
    bind_escalation_health_subject_metadata,
    run_care_safety_producer_for_subject,
)
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.canonical_policy import evaluate_i10_canonical_policy, resolve_i10_policy_risk
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import I10DecisionValue, I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.intelligence.contracts import (
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.safety_risk import REGISTRY_VERSION
from backend.app.services.section10.i4_emergency_escalation import persist_i4_emergency_escalation
from backend.app.services.section10.i4_escalation_provenance import new_occurrence_id

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
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
def sh1_env():
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


def _safety_meta(**extra) -> dict:
    meta = {
        "policy_risk_level": CARE_SAFETY_INTERRUPTION_POLICY_RISK,
        "policy_risk_source": CARE_SAFETY_POLICY_RISK_SOURCE,
        "template_key": "care_safety_escalation",
        "category": "health_alert",
    }
    meta.update(extra)
    return meta


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


def _emergency_assessment() -> RiskAssessment:
    return RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=RiskLevel.EMERGENCY,
        action=SafetyAction.RETURN_EMERGENCY_RESPONSE,
        domain=RiskDomain.MEDICAL_EMERGENCY,
        rule_id="i4.rule.emergency.medical.v1",
        language="en",
    )


def _setup_safety_care_network(db):
    owner = _user(db, "sh1-owner")
    cg = _user(db, "sh1-cg")
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
    db.add(models.PushDevice(user_id=cg.id, platform="android", fcm_token="fcm-sh1", is_active=True))
    db.add(
        models.NotificationPrefs(
            user_id=cg.id,
            companion_enabled=True,
            health_alert_enabled=True,
            quiet_hours_enabled=True,
            quiet_start="00:00",
            quiet_end="23:59",
        )
    )
    db.commit()
    return owner, cg, subject


def _authoritative_escalation(db, owner, subject):
    rec = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    assert rec is not None
    return rec


# FINDING-01 — explicit policy risk only


def test_forged_semantic_family_without_source_not_critical(db, sh1_env):
    cand = _candidate(
        semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    assert resolve_i10_policy_risk(cand, {}) == SmartNotificationRisk.NORMAL.value
    outcome = evaluate_i10_canonical_policy(db, candidate=cand)
    assert outcome.decision != I10DecisionValue.SEND or outcome.reason_code != "CRITICAL_ALLOWED"


def test_forged_critical_without_approved_source_not_critical(db, sh1_env):
    cand = _candidate(
        semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    forged = {"policy_risk_level": "critical", "policy_risk_source": "FORGED"}
    assert resolve_i10_policy_risk(cand, forged) == SmartNotificationRisk.NORMAL.value


def test_b16_authoritative_flow_carries_explicit_critical(db, sh1_env):
    owner, cg, subject = _setup_safety_care_network(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True, commit=True)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg.id)
        .one()
    )
    meta = json.loads(intent.payload_metadata_json)
    assert meta["policy_risk_level"] == CARE_SAFETY_INTERRUPTION_POLICY_RISK
    assert meta["policy_risk_source"] == CARE_SAFETY_POLICY_RISK_SOURCE
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg.id).one()
    assert notif.risk_level == CARE_SAFETY_INTERRUPTION_POLICY_RISK


# FINDING-02 — B14 proven gap only


def _status_overlap_meta(*, episode: str = "2026-08-31", data_status: str = "STALE_DATA") -> dict:
    return {
        "trigger_reason": "care_status_digest",
        "data_status": data_status,
        "schedule_label": episode,
    }


def test_b14_no_matching_gap_keep_both(db, sh1_env):
    owner = _user(db, "b14-keep")
    cg = _user(db, "b14-keep-cg")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    db.commit()
    meta = _status_overlap_meta()
    overlap = evaluate_b14_overlap(
        db,
        semantic_family=I10SemanticFamily.CARE_STATUS_DIGEST,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        payload_metadata=meta,
    )
    assert overlap.reason_code == B14_OVERLAP_REASON_KEEP_BOTH
    assert overlap.suppress_status_digest is False
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        semantic_family=I10SemanticFamily.CARE_STATUS_DIGEST,
    )
    outcome = evaluate_i10_canonical_policy(db, candidate=cand, payload_metadata=meta)
    assert outcome.reason_code != B14_OVERLAP_REASON_STATUS_REDUNDANT


def test_b14_matching_gap_suppresses_status(db, sh1_env):
    owner = _user(db, "b14-sup")
    cg = _user(db, "b14-sup-cg")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    episode = "2026-08-31"
    meta = _status_overlap_meta(episode=episode)
    create_i10_caregiver_delivery_intent(
        db,
        owner_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        occurrence_key=f"gap:{episode}",
        semantic_family=I10SemanticFamily.CARE_DATA_GAP,
        payload_metadata={
            "trigger_reason": "care_data_gap",
            "data_status": "STALE_DATA",
            "gap_episode_end": episode,
        },
        commit=True,
    )
    overlap = evaluate_b14_overlap(
        db,
        semantic_family=I10SemanticFamily.CARE_STATUS_DIGEST,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        payload_metadata=meta,
    )
    assert overlap.suppress_status_digest is True
    assert overlap.reason_code == B14_OVERLAP_REASON_STATUS_REDUNDANT


def test_b14_recipient_isolation(db, sh1_env):
    owner = _user(db, "b14-iso-r")
    cg_a = _user(db, "b14-iso-a")
    cg_b = _user(db, "b14-iso-b")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    episode = "2026-08-31"
    for cg in (cg_a, cg_b):
        grant_caregiver_subject_access(
            db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
        )
    create_i10_caregiver_delivery_intent(
        db,
        owner_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        occurrence_key=f"gap-a:{episode}",
        semantic_family=I10SemanticFamily.CARE_DATA_GAP,
        payload_metadata={
            "trigger_reason": "care_data_gap",
            "data_status": "STALE_DATA",
            "gap_episode_end": episode,
        },
        commit=True,
    )
    meta = _status_overlap_meta(episode=episode)
    for recipient, expect_suppress in ((cg_a, True), (cg_b, False)):
        overlap = evaluate_b14_overlap(
            db,
            semantic_family=I10SemanticFamily.CARE_STATUS_DIGEST,
            health_subject_id=subject.id,
            recipient_user_id=recipient.id,
            payload_metadata=meta,
        )
        assert overlap.suppress_status_digest is expect_suppress


def test_b14_subject_isolation(db, sh1_env):
    owner = _user(db, "b14-iso-s")
    cg = _user(db, "b14-iso-s-cg")
    subject_a = ensure_self_subject_for_account(db, owner.id, commit=True)
    subject_b = ensure_self_subject_for_account(db, _user(db, "other-subj").id, commit=True)
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject_a.id, recipient_account_user_id=cg.id
    )
    episode = "2026-08-31"
    create_i10_caregiver_delivery_intent(
        db,
        owner_user_id=owner.id,
        health_subject_id=subject_a.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        occurrence_key=f"gap-subj-a:{episode}",
        semantic_family=I10SemanticFamily.CARE_DATA_GAP,
        payload_metadata={
            "trigger_reason": "care_data_gap",
            "data_status": "STALE_DATA",
            "gap_episode_end": episode,
        },
        commit=True,
    )
    overlap = evaluate_b14_overlap(
        db,
        semantic_family=I10SemanticFamily.CARE_STATUS_DIGEST,
        health_subject_id=subject_b.id,
        recipient_user_id=cg.id,
        payload_metadata=_status_overlap_meta(episode=episode),
    )
    assert overlap.suppress_status_digest is False


def test_b14_episode_isolation(db, sh1_env):
    owner = _user(db, "b14-iso-e")
    cg = _user(db, "b14-iso-e-cg")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    create_i10_caregiver_delivery_intent(
        db,
        owner_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        occurrence_key="gap:2026-08-30",
        semantic_family=I10SemanticFamily.CARE_DATA_GAP,
        payload_metadata={
            "trigger_reason": "care_data_gap",
            "data_status": "STALE_DATA",
            "gap_episode_end": "2026-08-30",
        },
        commit=True,
    )
    overlap = evaluate_b14_overlap(
        db,
        semantic_family=I10SemanticFamily.CARE_STATUS_DIGEST,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        payload_metadata=_status_overlap_meta(episode="2026-08-31"),
    )
    assert overlap.suppress_status_digest is False


def test_care_safety_never_bundled_by_b14(db, sh1_env):
    owner = _user(db, "b14-safe")
    cg = _user(db, "b14-safe-cg")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    create_i10_caregiver_delivery_intent(
        db,
        owner_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        occurrence_key="gap:safety",
        semantic_family=I10SemanticFamily.CARE_DATA_GAP,
        payload_metadata={"data_status": "STALE_DATA", "gap_episode_end": "2026-08-31"},
        commit=True,
    )
    overlap = evaluate_b14_overlap(
        db,
        semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        payload_metadata={},
    )
    assert overlap.suppress_status_digest is False
    assert overlap.reason_code == "CARE_SAFETY_NEVER_BUNDLED"


# FINDING-03 — canonical-path integration


def test_talk_later_defers_canonical_candidate(db, sh1_env, client):
    user = _user(db, "talk-later")
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
        body="Body",
        channel="companion",
        category="companion",
        template_key="companion_ping",
        health_subject_id=subject.id,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    r = _feedback(client, user, notif.id, {"reaction": "interact", "action_id": "TALK_LATER"})
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
    assert outcome.decision == I10DecisionValue.DEFER
    assert outcome.reason_code == "FEEDBACK_TALK_LATER_DEFER"
    assert outcome.defer_until is not None


def test_feedback_expiry_restores_eligibility(db, sh1_env, client):
    user = _user(db, "fb-exp")
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
        body="Body",
        channel="companion",
        category="companion",
        template_key="companion_ping",
        health_subject_id=subject.id,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    base = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    _feedback(client, user, notif.id, {"reaction": "interact", "action_id": "NOT_NOW"})
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=user.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    meta = {"template_key": "companion_ping", "category": "companion"}
    blocked = evaluate_i10_canonical_policy(
        db, candidate=cand, payload_metadata=meta, notification_type="companion_ping", now_utc=base
    )
    assert blocked.decision == I10DecisionValue.SUPPRESS
    after = base + timedelta(hours=NOT_NOW_SUPPRESS_HOURS + 1)
    restored = evaluate_i10_canonical_policy(
        db, candidate=cand, payload_metadata=meta, notification_type="companion_ping", now_utc=after
    )
    assert restored.decision == I10DecisionValue.SEND


def test_critical_bypasses_active_conversation(db, sh1_env):
    owner, cg, subject = _setup_safety_care_network(db)
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    db.add(
        models.InteractionEvent(
            user_id=cg.id,
            event_type="chat_message",
            source="chat",
            interaction_channel="text",
            created_at=now.replace(tzinfo=None),
        )
    )
    db.commit()
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
        semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
        candidate_key="i10:safety:active-chat",
    )
    outcome = evaluate_i10_canonical_policy(
        db, candidate=cand, payload_metadata=_safety_meta(), now_utc=now
    )
    assert outcome.decision == I10DecisionValue.SEND
    assert outcome.reason_code == "CRITICAL_ALLOWED"


def test_critical_bypasses_feedback_cooldown(db, sh1_env, client):
    owner, cg, subject = _setup_safety_care_network(db)
    notif = models.Notification(
        user_id=cg.id,
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
    _feedback(client, cg, notif.id, {"reaction": "interact", "action_id": "NOT_NOW"})
    cand = _candidate(
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
        semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
        candidate_key="i10:safety:feedback",
    )
    outcome = evaluate_i10_canonical_policy(db, candidate=cand, payload_metadata=_safety_meta())
    assert outcome.decision == I10DecisionValue.SEND
    assert outcome.reason_code == "CRITICAL_ALLOWED"


def test_critical_access_revoke_blocks_delivery(db, sh1_env):
    owner, cg, subject = _setup_safety_care_network(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False, commit=True)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg.id)
        .one()
    )
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"
    assert db.query(models.Notification).filter(models.Notification.user_id == cg.id).count() == 0


def test_critical_grant_revoke_blocks_delivery(db, sh1_env):
    owner, cg, subject = _setup_safety_care_network(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False, commit=True)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg.id)
        .one()
    )
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"


def test_critical_caregiver_pref_off_blocks_delivery(db, sh1_env):
    owner, cg, subject = _setup_safety_care_network(db)
    prefs = db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == cg.id).one()
    prefs.health_alert_enabled = False
    db.commit()
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True, commit=True)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg.id).count() == 0
    decision = db.query(models.I10NotificationDecision).one()
    assert decision.decision == "SUPPRESS"


def test_duplicate_same_occurrence_one_outcome(db, sh1_env):
    owner, cg, subject = _setup_safety_care_network(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False, commit=True)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg.id)
        .one()
    )
    first = process_caregiver_delivery_intent(db, intent, commit=True)
    second = process_caregiver_delivery_intent(db, intent, commit=True)
    assert first["status"] == "processed"
    assert second["status"] == "processed"
    assert db.query(models.Notification).filter(models.Notification.user_id == cg.id).count() == 1


def test_new_occurrence_allowed_independently(db, sh1_env):
    owner, cg, subject = _setup_safety_care_network(db)
    rec1 = _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True, commit=True)
    rec2 = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    assert rec2 is not None
    from backend.app.services.section10.emergency_escalation_service import transition_escalation_state

    if rec2.current_state != "caregiver_escalation_ready":
        rec2 = transition_escalation_state(db, rec2, "caregiver_escalation_ready")
    bind_escalation_health_subject_metadata(db, rec2, health_subject_id=subject.id)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True, commit=True)
    assert rec2.id != rec1.id
    assert db.query(models.Notification).filter(models.Notification.user_id == cg.id).count() == 2


def test_notification_to_chat_preserves_context(db, sh1_env, client):
    owner, cg, subject = _setup_safety_care_network(db)
    _authoritative_escalation(db, owner, subject)
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True, commit=True)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg.id).one()
    assert notif.health_subject_id == subject.id
    r = client.post(
        "/interact/chat",
        json={"message": "about this notice", "source_notification_id": notif.id},
        headers=_auth(cg),
    )
    assert r.status_code == 200
    assert r.json().get("continued_from_notification") is True
    other = _user(db, "sh1-stranger")
    denied = client.post(
        "/interact/chat",
        json={"message": "hack", "source_notification_id": notif.id},
        headers=_auth(other),
    )
    assert denied.status_code == 403


def test_intake_transaction_failure_retry_safe(db, sh1_env):
    owner = _user(db, "tx-fail")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=owner.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=owner.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    db.add(
        models.NotificationPrefs(
            user_id=owner.id,
            companion_enabled=True,
            health_alert_enabled=True,
        )
    )
    db.commit()
    cand = _candidate(
        candidate_key="i10:tx:fail:1",
        health_subject_id=subject.id,
        recipient_user_id=owner.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    payload = NotificationPayload(
        user_id=owner.id,
        type="health_alert",
        title="T",
        body="B",
        priority="normal",
        dedupe_key="i10:tx:fail:1",
        health_subject_id=subject.id,
        semantic_family=I10SemanticFamily.GENERAL_STATUS.value,
    )
    calls = {"n": 0}

    def _fail_once(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("persist_fail")
        from backend.app.services.notification_engine import NotificationBuilder as RealBuilder

        return RealBuilder.persist(self, *args, **kwargs)

    with patch("backend.app.services.notification_engine.NotificationBuilder.persist", _fail_once):
        with pytest.raises(RuntimeError):
            enqueue_i10_notification(db, candidate=cand, payload=payload)
        db.rollback()

    result = enqueue_i10_notification(db, candidate=cand, payload=payload)
    assert result.decision == I10DecisionValue.SEND
    assert result.notification_id is not None
    assert db.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 1
