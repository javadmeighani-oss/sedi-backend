"""I10-B16-A01 — I4 → Section10 authoritative safety escalation seam (PostgreSQL + FastAPI)."""

from __future__ import annotations

import ast
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access, revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import (
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.care_safety_producer_worker import run_care_safety_producer_for_subject
from backend.app.services.i10.i4_escalation_authority import is_authoritative_care_safety_escalation
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.intelligence.contracts import (
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.safety_risk import (
    REGISTRY_VERSION,
    assess_safety_risk,
    fail_closed_assessment,
)
from backend.app.services.section10.emergency_escalation_service import (
    create_escalation_record,
    transition_escalation_state,
)
from backend.app.services.section10.i4_emergency_escalation import persist_i4_emergency_escalation
from backend.app.services.section10.i4_escalation_provenance import (
    AUTHORITY_SOURCE,
    AUTHORITY_VERSION,
    new_occurrence_id,
    parse_escalation_metadata,
    record_has_valid_i4_provenance,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_EMERGENCY_MESSAGE = "I have chest pain"
_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
    },
    clear=False,
)
_BRAIN_PATCH = patch(
    "backend.app.core.conversation.brain.ConversationBrain.process_message",
    return_value={"message": "Ok", "language": "en"},
)
_REMINDER_PATCH = patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
_CMD_PATCH = patch(
    "backend.app.services.chat_commands.detect_and_handle_user_settings_command",
    return_value=None,
)


@pytest.fixture
def a01_patches():
    with _GATE4_PATCH, _FLAG_PATCH, _BRAIN_PATCH, _REMINDER_PATCH, _CMD_PATCH:
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


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{uuid4().hex[:8]}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _push(db, user_id: int, token: str) -> None:
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=token, is_active=True))
    db.commit()


def _prefs(db, user_id: int, *, health_alert_enabled: bool = True) -> None:
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=True,
            health_alert_enabled=health_alert_enabled,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()


def _emergency_assessment() -> RiskAssessment:
    return RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=RiskLevel.EMERGENCY,
        action=SafetyAction.RETURN_EMERGENCY_RESPONSE,
        domain=RiskDomain.MEDICAL_EMERGENCY,
        rule_id="i4.rule.emergency.medical.v1",
        language="en",
    )


def _setup_self_care_network(db, *, extra_scopes: tuple[I10NotificationScope, ...] = ()):
    owner = _user(db, "owner")
    cg = _user(db, "cg")
    subject = ensure_self_subject_for_account(db, owner.id, display_name="Self", commit=True)
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
    for scope in extra_scopes:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg.id,
            notification_scope=scope,
        )
    _push(db, cg.id, f"fcm-{cg.id}")
    _prefs(db, cg.id)
    return owner, cg, subject


def _forge_ready(db, owner, subject, meta: dict) -> models.EmergencyEscalationRecord:
    rec = models.EmergencyEscalationRecord(
        owner_user_id=owner.id,
        reason_category="forged",
        policy_version="v1",
        current_state="caregiver_escalation_ready",
        attempt_count=0,
        metadata_json=json.dumps(meta, ensure_ascii=False),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _chat(client, user: models.User, message: str, **extra):
    payload = {"message": message, **extra}
    return client.post("/interact/chat", json=payload, headers=_auth(user.id))


def test_real_fastapi_i4_emergency_to_ledger_and_care_network(client, db, a01_patches):
    owner, cg, subject = _setup_self_care_network(db)
    resp = _chat(client, owner, _EMERGENCY_MESSAGE)
    assert resp.status_code == 200
    body = resp.json()
    assert "emergency" in body["message"].lower()
    assert "risk_level" not in body

    rec = db.query(models.EmergencyEscalationRecord).one()
    assert rec.current_state == "caregiver_escalation_ready"
    assert rec.owner_user_id == owner.id
    meta = parse_escalation_metadata(rec.metadata_json)
    assert record_has_valid_i4_provenance(rec)
    assert meta["authority_source"] == AUTHORITY_SOURCE
    assert meta["authority_version"] == AUTHORITY_VERSION
    assert meta["risk_level"] == "emergency"
    assert meta["safety_action"] == "return_emergency_response"
    assert meta["registry_version"] == REGISTRY_VERSION
    assert meta["rule_id"] == "i4.rule.emergency.medical.v1"
    assert meta["health_subject_id"] == subject.id
    blob = json.dumps(meta)
    assert _EMERGENCY_MESSAGE.lower() not in blob.lower()
    assert "chest pain" not in blob.lower()

    notif = db.query(models.Notification).filter(models.Notification.user_id == cg.id).one()
    assert notif.health_subject_id == subject.id
    assert notif.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value
    intent = db.query(models.CaregiverNotificationIntent).one()
    assert intent.i10_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == intent.i10_decision_id
    ).one()
    assert decision.decision == "SEND"

    follow = _chat(client, cg, "about this notice", source_notification_id=notif.id)
    assert follow.status_code == 200
    assert follow.json().get("continued_from_notification") is True


def test_informational_emergency_phrase_no_escalation(client, db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    resp = _chat(client, owner, "What are the symptoms of a heart attack?")
    assert resp.status_code == 200
    assert db.query(models.EmergencyEscalationRecord).count() == 0
    assert db.query(models.Notification).count() == 0


def test_negated_emergency_phrase_no_escalation(client, db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    resp = _chat(client, owner, "I am not suicidal")
    assert resp.status_code == 200
    assert db.query(models.EmergencyEscalationRecord).count() == 0


def test_high_no_caregiver_escalation(client, db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    resp = _chat(client, owner, "I have slurred speech now")
    assert resp.status_code == 200
    assert db.query(models.EmergencyEscalationRecord).count() == 0
    assert db.query(models.Notification).count() == 0


def test_caution_no_caregiver_escalation(client, db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    resp = _chat(client, owner, "I want to change my dose")
    assert resp.status_code == 200
    assert db.query(models.EmergencyEscalationRecord).count() == 0


def test_none_no_caregiver_escalation(client, db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    resp = _chat(client, owner, "hello")
    assert resp.status_code == 200
    assert db.query(models.EmergencyEscalationRecord).count() == 0


def test_fail_closed_no_caregiver_escalation(client, db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    closed = fail_closed_assessment(language="en")
    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.precheck_safety_risk",
        return_value=closed,
    ):
        resp = _chat(client, owner, _EMERGENCY_MESSAGE)
    assert resp.status_code == 200
    assert db.query(models.EmergencyEscalationRecord).count() == 0
    assert db.query(models.Notification).count() == 0


def test_manual_ready_without_provenance_transition_denied(db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    rec = create_escalation_record(db, owner.id, "inactivity")
    with pytest.raises(ValueError, match="ready_state_requires_i4_provenance"):
        transition_escalation_state(db, rec, "caregiver_escalation_ready")
    db.refresh(rec)
    assert rec.current_state == "monitoring"


def test_manual_ready_without_provenance_b16_denied(db, a01_patches):
    owner, _, subject = _setup_self_care_network(db)
    rec = _forge_ready(db, owner, subject, {"health_subject_id": subject.id})
    assert rec.current_state == "caregiver_escalation_ready"
    assert is_authoritative_care_safety_escalation(rec) is False
    outcome = run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True)
    assert outcome["intents"] == 0
    assert db.query(models.Notification).count() == 0


@pytest.mark.parametrize(
    "meta_patch",
    [
        {"authority_source": "FORGED"},
        {"risk_level": "high"},
        {"safety_action": "fail_closed_response"},
    ],
)
def test_forged_provenance_b16_denied(db, a01_patches, meta_patch):
    owner, _, subject = _setup_self_care_network(db)
    meta = {
        "authority_source": AUTHORITY_SOURCE,
        "authority_version": AUTHORITY_VERSION,
        "registry_version": REGISTRY_VERSION,
        "rule_id": "i4.rule.emergency.medical.v1",
        "risk_level": "emergency",
        "safety_action": "return_emergency_response",
        "risk_domain": "medical_emergency",
        "language": "en",
        "occurred_at": "2026-09-01T00:00:00Z",
        "health_subject_id": subject.id,
        "occurrence_id": new_occurrence_id(),
    }
    meta.update(meta_patch)
    rec = _forge_ready(db, owner, subject, meta)
    assert is_authoritative_care_safety_escalation(rec) is False
    outcome = run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True)
    assert outcome["intents"] == 0


def test_resolved_escalation_refused(db, a01_patches):
    owner, _, subject = _setup_self_care_network(db)
    rec = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    rec = transition_escalation_state(db, rec, "resolved", resolution_source="test")
    assert is_authoritative_care_safety_escalation(rec) is False
    outcome = run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True)
    assert outcome["intents"] == 0


@pytest.mark.parametrize(
    "scope",
    [
        I10NotificationScope.GENERAL_STATUS,
        I10NotificationScope.DEVICE_STATUS,
        I10NotificationScope.CARE_ACTION,
        I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
    ],
)
def test_unrelated_scope_denied(db, a01_patches, scope):
    owner = _user(db, "owner-scope")
    cg = _user(db, "cg-scope")
    subject = ensure_self_subject_for_account(db, owner.id, commit=True)
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
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg.id).count() == 0


def test_access_revoke_before_delivery_suppressed(db, a01_patches):
    owner, cg, subject = _setup_self_care_network(db)
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intent = db.query(models.CaregiverNotificationIntent).one()
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent

    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "suppressed"


def test_safety_grant_revoke_before_delivery_suppressed(db, a01_patches):
    owner, cg, subject = _setup_self_care_network(db)
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intent = db.query(models.CaregiverNotificationIntent).one()
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent

    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "suppressed"


def test_pref_disabled_suppressed(db, a01_patches):
    owner, cg, subject = _setup_self_care_network(db)
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == cg.id).update(
        {"health_alert_enabled": False}
    )
    db.commit()
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=False)
    intent = db.query(models.CaregiverNotificationIntent).one()
    from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent

    process_caregiver_delivery_intent(db, intent)
    assert intent.status == "suppressed"


def test_multi_caregiver_independent(db, a01_patches):
    owner, cg_a, subject = _setup_self_care_network(db)
    cg_b = _user(db, "cg-b")
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg_b.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_b.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    _push(db, cg_b.id, f"fcm-{cg_b.id}")
    _prefs(db, cg_b.id)
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_b.id).count() == 1


def test_revoked_chat_context_fail_closed(client, db, a01_patches):
    owner, cg, subject = _setup_self_care_network(db)
    resp = _chat(client, owner, _EMERGENCY_MESSAGE)
    assert resp.status_code == 200
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg.id).one()
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    follow = _chat(client, cg, "about this notice", source_notification_id=notif.id)
    assert follow.status_code in (200, 403)
    if follow.status_code == 200:
        from backend.app.services.gate4.notification_chat_context import build_safe_chat_context

        ctx = build_safe_chat_context(notif, db=db, viewer_user_id=cg.id)
        assert ctx.get("subject_context_available") == "false"


def test_cross_user_notification_chat_blocked(client, db, a01_patches):
    owner, cg, _ = _setup_self_care_network(db)
    other = _user(db, "other")
    resp = _chat(client, owner, _EMERGENCY_MESSAGE)
    assert resp.status_code == 200
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg.id).one()
    follow = _chat(client, other, "hi", source_notification_id=notif.id)
    assert follow.status_code == 403


def test_persistence_failure_preserves_user_safety_response(client, db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    with patch(
        "backend.app.services.section10.i4_emergency_escalation.persist_i4_emergency_escalation",
        side_effect=RuntimeError("bounded_db_failure"),
    ):
        resp = _chat(client, owner, _EMERGENCY_MESSAGE)
    assert resp.status_code == 200
    assert "emergency" in resp.json()["message"].lower()
    assert db.query(models.EmergencyEscalationRecord).count() == 0
    assert db.query(models.CaregiverNotificationIntent).count() == 0
    assert db.query(models.Notification).count() == 0


def test_idempotent_same_occurrence(db, a01_patches):
    owner, _, subject = _setup_self_care_network(db)
    occ = new_occurrence_id()
    first = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=occ,
        commit=True,
    )
    second = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=occ,
        commit=True,
    )
    assert first is not None and second is not None
    assert first.id == second.id
    assert db.query(models.EmergencyEscalationRecord).count() == 1


def test_new_occurrence_allowed(db, a01_patches):
    owner, _, subject = _setup_self_care_network(db)
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    assert db.query(models.EmergencyEscalationRecord).count() == 2


def test_transaction_retry_does_not_duplicate(db, a01_patches):
    owner, _, _ = _setup_self_care_network(db)
    calls = {"n": 0}
    real = persist_i4_emergency_escalation

    def _post_commit_fail(*args, **kwargs):
        rec = real(*args, **kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("post_commit_retry")
        return rec

    with patch(
        "backend.app.services.section10.i4_emergency_escalation.persist_i4_emergency_escalation",
        side_effect=_post_commit_fail,
    ):
        from backend.app.services.section10.i4_emergency_escalation import (
            attempt_i4_emergency_escalation_from_interact,
        )

        attempt_i4_emergency_escalation_from_interact(
            db,
            authenticated_user_id=owner.id,
            risk_assessment=_emergency_assessment(),
        )
    assert calls["n"] == 2
    assert db.query(models.EmergencyEscalationRecord).count() == 1


def test_high_and_fail_closed_persist_rejected(db, a01_patches):
    owner, _, subject = _setup_self_care_network(db)
    high = assess_safety_risk(message="I have slurred speech now", language="en")
    assert high.level is RiskLevel.HIGH
    assert persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=high,
        commit=True,
    ) is None
    closed = fail_closed_assessment(language="en")
    assert persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=closed,
        commit=True,
    ) is None
    assert db.query(models.EmergencyEscalationRecord).count() == 0


def test_reason_category_absent_without_detail_scope(db, a01_patches):
    owner, cg, subject = _setup_self_care_network(db)
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True)
    intent = db.query(models.CaregiverNotificationIntent).one()
    payload = json.loads(intent.payload_metadata_json or "{}")
    assert "reason_category" not in payload
    assert "reason_category" not in (payload.get("context") or {})
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg.id).one()
    assert "reason_category" not in (notif.body or "")
    assert "medical_emergency" not in (notif.body or "")
    ctx = notif.context_json or ""
    assert "reason_category" not in ctx


def test_reason_category_present_with_detail_scope(db, a01_patches):
    owner, cg, subject = _setup_self_care_network(
        db, extra_scopes=(I10NotificationScope.SENSITIVE_HEALTH_DETAIL,)
    )
    persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True)
    intent = db.query(models.CaregiverNotificationIntent).one()
    payload = json.loads(intent.payload_metadata_json or "{}")
    assert payload.get("reason_category") == "medical_emergency"
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg.id).one()
    assert "medical_emergency" in (notif.body or "")


def test_flags_default_off_no_notification(client, db):
    owner, cg, _ = _setup_self_care_network(db)
    with _BRAIN_PATCH, _REMINDER_PATCH, _CMD_PATCH:
        resp = _chat(client, owner, _EMERGENCY_MESSAGE)
    assert resp.status_code == 200
    assert db.query(models.EmergencyEscalationRecord).count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == cg.id).count() == 0


def test_no_direct_notification_orm_in_seam():
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    files = [
        root / "section10" / "i4_emergency_escalation.py",
        root / "section10" / "i4_escalation_provenance.py",
        root / "i10" / "care_safety_producer_worker.py",
        root / "i10" / "care_safety_copy.py",
        root / "i10" / "i4_escalation_authority.py",
    ]
    for path in files:
        dumped = ast.dump(ast.parse(path.read_text(encoding="utf-8")))
        assert "Notification(" not in dumped
        text = path.read_text(encoding="utf-8")
        assert "send_push" not in text
        assert "firebase_admin" not in text
