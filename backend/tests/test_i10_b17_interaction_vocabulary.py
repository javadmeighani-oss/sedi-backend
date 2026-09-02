"""I10-B17 — interaction vocabulary alignment + domain-safe action semantics (PostgreSQL + FastAPI)."""

from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytz
from fastapi.testclient import TestClient
from sqlalchemy import func

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access, revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import create_subject_notification_grant
from backend.app.services.i10.care_safety_producer_worker import run_care_safety_producer_for_subject
from backend.app.services.i10.event_reminder_i10_adapter import DOCTOR_EVENT_TYPE
from backend.app.services.i10.interaction_vocabulary import (
    APPOINTMENT_ATTENDANCE_AUTHORITY,
    CARE_ACTION_COMPLETION_AUTHORITY,
    I8_ACTION_COMPLETION_AUTHORITY,
    MEDICATION_CONFIRM_AUTHORITY,
    SAFETY_RESOLUTION_AUTHORITY,
    VOCABULARY_VERSION,
)
from backend.app.services.i10.managed_i8_action_binding import build_health_subject_context_refs_json
from backend.app.services.i10.medication_adherence import MedicationAdherenceState
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account, ensure_self_subject_for_account
from backend.app.services.medication_scheduler import process_medication_reminders
from backend.app.services.notification_engine import DecisionEngine
from backend.app.services.section10.event_reminder_scheduler import process_event_reminders
from backend.app.services.intelligence.contracts import (
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.safety_risk import REGISTRY_VERSION
from backend.app.services.section10.i4_emergency_escalation import persist_i4_emergency_escalation
from backend.app.services.section10.i4_escalation_provenance import new_occurrence_id, parse_escalation_metadata

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
    },
    clear=False,
)
_EVENT_FLAG = patch(
    "backend.app.services.section10.feature_flags.event_reminder_scheduler_enabled",
    return_value=True,
)
_COACHING_FLAG = patch(
    "backend.app.services.i10.coaching_worker.coaching_followup_enabled",
    return_value=True,
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
def b17_patches():
    with _GATE4_PATCH, _FLAG_PATCH, _EVENT_FLAG, _COACHING_FLAG, _BRAIN_PATCH, _REMINDER_PATCH, _CMD_PATCH:
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
    ensure_self_subject_for_account(db, row.id, commit=True)
    return row


def _med_setup(db, user: models.User):
    med = models.Medication(name="B17Med", default_dosage="5mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    um = models.UserMedication(
        user_id=user.id,
        medication_id=med.id,
        interval_hours=8,
        user_dosage="5mg",
        reminder_enabled=True,
        timezone="Asia/Tehran",
    )
    db.add(um)
    db.commit()
    db.refresh(um)
    db.add(models.UserMedicationSchedule(user_medication_id=um.id, time_of_day=time(8, 0)))
    db.commit()
    return um


def _due_utc(hour: int = 8, minute: int = 5) -> datetime:
    tehran = pytz.timezone("Asia/Tehran")
    local = tehran.localize(datetime(2026, 6, 29, hour, minute, 0))
    return local.astimezone(pytz.UTC).replace(tzinfo=None)


def _med_notification(db, b17_patches):
    user = _user(db, "med")
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc())
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    return user, notif


def _feedback(client, user: models.User, notif_id: int, payload: dict):
    return client.post(f"/notifications/{notif_id}/feedback", json=payload, headers=_auth(user.id))


# A — SELF basic interaction


def test_self_like_persists_feedback_and_interaction_event(client, db, b17_patches):
    user = _user(db, "self-like")
    notif = models.Notification(
        user_id=user.id,
        type="companion",
        title="Hello",
        body="Check in",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    r = _feedback(client, user, notif.id, {"reaction": "like"})
    assert r.status_code == 200
    fb = db.query(models.NotificationFeedback).filter_by(notification_id=notif.id).one()
    assert fb.action == "like"
    evt = db.query(models.InteractionEvent).filter_by(source_notification_id=notif.id).one()
    assert evt.event_type == "notification_like"
    meta = json.loads(evt.metadata_json)
    assert meta["canonical_verb"] == "LIKE"
    assert meta["vocabulary_version"] == VOCABULARY_VERSION


def test_mark_read_records_read_event_once(client, db, b17_patches):
    user = _user(db, "read-user")
    notif = models.Notification(
        user_id=user.id,
        type="reminder",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    r1 = client.post(f"/notifications/{notif.id}/mark-read", headers=_auth(user.id), params={"user_id": user.id})
    assert r1.status_code == 200
    assert r1.json()["data"]["canonical_verb"] == "READ"
    read_events = (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.source_notification_id == notif.id,
            models.InteractionEvent.event_type == "notification_read",
        )
        .all()
    )
    assert len(read_events) == 1

    r2 = client.post(f"/notifications/{notif.id}/mark-read", headers=_auth(user.id), params={"user_id": user.id})
    assert r2.status_code == 200
    assert (
        db.query(func.count(models.InteractionEvent.id))
        .filter(
            models.InteractionEvent.source_notification_id == notif.id,
            models.InteractionEvent.event_type == "notification_read",
        )
        .scalar()
        == 1
    )


# B — medication authority boundary


def test_medication_generic_ack_does_not_confirm_taken(client, db, b17_patches):
    user, notif = _med_notification(db, b17_patches)
    r = _feedback(client, user, notif.id, {"reaction": "interact", "action_id": "ACK_THANKS"})
    assert r.status_code == 200
    occ = db.query(models.MedicationDoseOccurrence).filter_by(source_notification_id=notif.id).one()
    assert occ.state == MedicationAdherenceState.DUE.value
    evt = (
        db.query(models.InteractionEvent)
        .filter_by(source_notification_id=notif.id)
        .order_by(models.InteractionEvent.id.desc())
        .first()
    )
    assert evt.event_type == "notification_ack"


def test_medication_dislike_does_not_confirm_taken(client, db, b17_patches):
    user, notif = _med_notification(db, b17_patches)
    r = _feedback(client, user, notif.id, {"reaction": "dislike", "reason": "too_frequent"})
    assert r.status_code == 200
    occ = db.query(models.MedicationDoseOccurrence).filter_by(source_notification_id=notif.id).one()
    assert occ.state == MedicationAdherenceState.DUE.value
    evt = db.query(models.InteractionEvent).filter_by(source_notification_id=notif.id).one()
    assert evt.event_type == "notification_dislike_reason"
    meta = json.loads(evt.metadata_json)
    assert meta["dislike_reason_bounded"] is True


def test_medication_confirm_taken_requires_b09_endpoint(client, db, b17_patches):
    user, notif = _med_notification(db, b17_patches)
    r = client.post(f"/notifications/{notif.id}/medication/confirm-taken", headers=_auth(user.id))
    assert r.status_code == 200
    assert r.json()["data"]["state"] == MedicationAdherenceState.CONFIRMED_TAKEN.value
    occ = db.query(models.MedicationDoseOccurrence).filter_by(source_notification_id=notif.id).one()
    assert occ.state == MedicationAdherenceState.CONFIRMED_TAKEN.value


# C — appointment non-inference


def test_appointment_ack_does_not_change_event_status(client, db, b17_patches):
    user = _user(db, "appt")
    starts = datetime.utcnow() + timedelta(minutes=60)
    ev = models.UserEvent(
        user_id=user.id,
        title="Dr Visit",
        event_type=DOCTOR_EVENT_TYPE,
        event_domain="medical",
        starts_at=starts,
        timezone="UTC",
        status="scheduled",
        reminder_enabled=True,
        reminder_offsets_json=json.dumps([60]),
    )
    db.add(ev)
    db.commit()
    process_event_reminders(db)
    notif = db.query(models.Notification).filter_by(user_id=user.id).one()
    assert notif.semantic_family == I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER.value

    r = _feedback(client, user, notif.id, {"reaction": "dislike"})
    assert r.status_code == 200
    db.refresh(ev)
    assert ev.status == "scheduled"


# D — coaching / I8 boundary


def test_coaching_ack_does_not_complete_i8_action(client, db, b17_patches):
    from backend.app.services.i10.coaching_worker import process_i8_coaching_followups

    user = _user(db, "coach")
    when = datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)
    db.add(models.UserProfileCore(user_id=user.id, timezone="UTC"))
    db.commit()
    window = resolve_local_day_window(db, user.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=user.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{user.id}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=user.id,
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_item",
        action_idempotency_key="walk-1",
        summary_text="Walk",
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    notif = db.query(models.Notification).filter_by(user_id=user.id).one()

    r = _feedback(client, user, notif.id, {"reaction": "interact", "action_id": "ACK_THANKS"})
    assert r.status_code == 200
    db.refresh(action)
    assert action.status == "ACTIVE"


# E — B15 care action boundary


def _care_action_notification(db):
    owner = _user(db, "ca-owner")
    cg = _user(db, "ca-cg")
    subject = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="Parent", access_role="MANAGER"
    )
    assert subject.linked_user_id is None
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
    db.add(models.PushDevice(user_id=cg.id, platform="android", fcm_token=f"fcm-{cg.id}", is_active=True))
    db.add(
        models.NotificationPrefs(
            user_id=cg.id,
            companion_enabled=True,
            health_alert_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()
    when = datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)
    db.add(models.UserProfileCore(user_id=owner.id, timezone="UTC"))
    db.commit()
    window = resolve_local_day_window(db, owner.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=owner.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{subject.id}",
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
        action_idempotency_key="care-1",
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
    notif = db.query(models.Notification).filter_by(user_id=cg.id).one()
    return owner, cg, subject, action, notif


def test_care_action_caregiver_ack_no_domain_completion(client, db, b17_patches):
    owner, cg, subject, action, notif = _care_action_notification(db)
    assert notif.health_subject_id == subject.id
    r = _feedback(client, cg, notif.id, {"reaction": "interact", "action_id": "ACK_THANKS"})
    assert r.status_code == 200
    db.refresh(action)
    assert action.status == "ACTIVE"
    fb = db.query(models.NotificationFeedback).filter_by(notification_id=notif.id).one()
    assert fb.user_id == cg.id


def _emergency_assessment() -> RiskAssessment:
    return RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=RiskLevel.EMERGENCY,
        action=SafetyAction.RETURN_EMERGENCY_RESPONSE,
        domain=RiskDomain.MEDICAL_EMERGENCY,
        rule_id="i4.rule.emergency.medical.v1",
        language="en",
    )


    owner = _user(db, "safety-owner")
    cg = _user(db, "safety-cg")
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
    db.add(models.PushDevice(user_id=cg.id, platform="android", fcm_token=f"fcm-{cg.id}", is_active=True))
    db.add(
        models.NotificationPrefs(
            user_id=cg.id,
            companion_enabled=True,
            health_alert_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()

    rec = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=owner.id,
        health_subject_id=subject.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    assert rec is not None
    before_meta = parse_escalation_metadata(rec.metadata_json)
    before_state = rec.current_state

    run_care_safety_producer_for_subject(db, health_subject_id=subject.id, deliver=True, commit=True)
    notif = db.query(models.Notification).filter_by(user_id=cg.id).one()

    r = _feedback(client, cg, notif.id, {"reaction": "like"})
    assert r.status_code == 200
    db.refresh(rec)
    after_meta = parse_escalation_metadata(rec.metadata_json)
    assert rec.current_state == before_state
    assert after_meta["risk_level"] == before_meta["risk_level"]
    assert after_meta["authority_source"] == before_meta["authority_source"]


# G — caregiver authorization


def test_cross_user_feedback_denied(client, db, b17_patches):
    owner, cg, _, _, notif = _care_action_notification(db)
    other = _user(db, "intruder")
    r = _feedback(client, other, notif.id, {"reaction": "like"})
    assert r.status_code == 403


def test_caregiver_authorized_feedback_allowed(client, db, b17_patches):
    _, cg, subject, _, notif = _care_action_notification(db)
    r = _feedback(client, cg, notif.id, {"reaction": "like"})
    assert r.status_code == 200
    evt = db.query(models.InteractionEvent).filter_by(source_notification_id=notif.id).one()
    assert evt.user_id == cg.id
    assert notif.health_subject_id == subject.id


def test_revoked_caregiver_chat_denied(client, db, b17_patches):
    owner, cg, subject, _, notif = _care_action_notification(db)
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    r = client.post(
        "/interact/chat",
        json={"message": "about this", "source_notification_id": notif.id},
        headers=_auth(cg.id),
    )
    assert r.status_code in (403, 404)


# H — source_notification_id chat continuation


def test_source_notification_id_chat_continuation(client, db, b17_patches):
    user = _user(db, "chat-user")
    notif = models.Notification(
        user_id=user.id,
        health_subject_id=ensure_self_subject_for_account(db, user.id, commit=True).id,
        type="companion",
        title="Hi",
        body="Body",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    r = client.post(
        "/interact/chat",
        json={"message": "tell me more", "source_notification_id": notif.id},
        headers=_auth(user.id),
    )
    assert r.status_code == 200
    evt = (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.source_notification_id == notif.id,
            models.InteractionEvent.event_type == "chat_message",
        )
        .one()
    )
    assert evt.user_id == user.id


# I — idempotency


def test_duplicate_ack_creates_ledger_rows_without_corruption(client, db, b17_patches):
    user = _user(db, "dup")
    notif = models.Notification(
        user_id=user.id,
        type="companion",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    payload = {"reaction": "interact", "action_id": "ACK_THANKS"}
    assert _feedback(client, user, notif.id, payload).status_code == 200
    assert _feedback(client, user, notif.id, payload).status_code == 200
    assert db.query(models.NotificationFeedback).filter_by(notification_id=notif.id).count() == 2
    events = db.query(models.InteractionEvent).filter_by(source_notification_id=notif.id).all()
    assert len(events) == 2
    assert all(e.event_type == "notification_ack" for e in events)


def test_dislike_separate_from_not_now_event_type(client, db, b17_patches):
    user = _user(db, "dislike")
    notif = models.Notification(
        user_id=user.id,
        type="companion",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    _feedback(client, user, notif.id, {"reaction": "dislike"})
    _feedback(client, user, notif.id, {"reaction": "interact", "action_id": "NOT_NOW"})
    types = [
        e.event_type
        for e in db.query(models.InteractionEvent)
        .filter_by(source_notification_id=notif.id)
        .order_by(models.InteractionEvent.id.asc())
        .all()
    ]
    assert types == ["notification_dislike", "notification_not_now"]


# J — transaction failure


def test_interaction_failure_rolls_back_without_partial_feedback(db, b17_patches):
    from backend.app.routers.notifications import submit_notification_feedback

    user = _user(db, "tx")
    notif = models.Notification(
        user_id=user.id,
        type="companion",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    notif_id = notif.id

    with patch(
        "backend.app.services.i10.interaction_recorder.create_interaction_event",
        side_effect=RuntimeError("ledger_fail"),
    ):
        with pytest.raises(RuntimeError):
            submit_notification_feedback(
                notification_id=notif_id,
                payload={"reaction": "like"},
                auth_user=user,
                user_id=None,
                db=db,
            )
        db.rollback()

    assert db.query(models.NotificationFeedback).filter_by(notification_id=notif_id).count() == 0
    assert db.query(models.InteractionEvent).filter_by(source_notification_id=notif_id).count() == 0


# Static vocabulary / authority constants


def test_vocabulary_authority_constants():
    assert MEDICATION_CONFIRM_AUTHORITY == "B09_MEDICATION_CONFIRM_TAKEN_ENDPOINT"
    assert APPOINTMENT_ATTENDANCE_AUTHORITY == "NONE_GENERIC"
    assert I8_ACTION_COMPLETION_AUTHORITY == "I8_OPERATIONAL_PLAN_ACTION_DOMAIN"
    assert CARE_ACTION_COMPLETION_AUTHORITY == "B15_I8_MANAGED_ACTION_DOMAIN"
    assert SAFETY_RESOLUTION_AUTHORITY == "SECTION10_I4_PROVENANCE_SEPARATE"


def test_done_payload_rejected_without_domain_endpoint(client, db, b17_patches):
    user = _user(db, "done")
    notif = models.Notification(
        user_id=user.id,
        type="companion",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    r = _feedback(client, user, notif.id, {"reaction": "interact", "action_id": "done"})
    assert r.status_code == 422
