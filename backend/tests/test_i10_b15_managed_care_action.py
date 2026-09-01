"""I10-B15 managed-subject I8 CARE_ACTION → Care Network (PostgreSQL)."""

from __future__ import annotations

import ast
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import func

from backend.app import models
from backend.app.schemas.chat import ChatRequest
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access, revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import create_subject_notification_grant, revoke_subject_notification_grant_by_scope
from backend.app.services.i10.care_digest_producer_worker import run_care_digest_producer_for_subject
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.managed_i8_action_binding import build_health_subject_context_refs_json
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account

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
def b15_patches():
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


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


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


def _setup_caregivers(
    db,
    *,
    cg_a_care_action: bool = True,
    cg_b_care_action: bool = False,
    cg_b_general: bool = False,
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
    if cg_a_care_action:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_a.id,
            notification_scope=I10NotificationScope.CARE_ACTION,
        )
    if cg_b_care_action:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_b.id,
            notification_scope=I10NotificationScope.CARE_ACTION,
        )
    if cg_b_general:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_b.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    return owner, cg_a, cg_b, subject


def _managed_action(
    db,
    owner: models.User,
    subject: models.HealthSubject,
    *,
    summary: str = "Evening medication reminder check",
    domain: str = "routine",
    when: datetime | None = None,
    action_key: str = "care-act-1",
) -> models.I8OperationalPlanAction:
    when = when or _when()
    _profile_tz(db, owner.id)
    window = resolve_local_day_window(db, owner.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=owner.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{subject.id}-{action_key}",
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
        action_idempotency_key=action_key,
        summary_text=summary,
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


def _run_pipeline(db, subject, when, *, deliver: bool = True) -> dict:
    return run_care_action_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=deliver, commit=True
    )


# A/B managed subject path


def test_managed_subject_action_real_path(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    action = _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg_a.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .one()
    )
    assert intent.status == "processed"
    notif = db.query(models.Notification).filter(models.Notification.id == intent.notification_id).one()
    assert notif.user_id == cg_a.id
    assert notif.health_subject_id == subject.id
    assert notif.health_subject_id != cg_a.id
    assert notif.semantic_family == I10SemanticFamily.CARE_ACTION.value
    assert intent.i10_decision_id is not None
    db.refresh(action)
    assert action.status == "ACTIVE"


def test_caregiver_not_substituted_as_subject(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    assert notif.health_subject_id == subject.id
    assert notif.user_id != subject.id


# C no invention


def test_no_i8_action_no_care_action(db, b15_patches):
    _, _, _, subject = _setup_caregivers(db)
    when = _when()
    outcome = _run_pipeline(db, subject, when)
    assert outcome["actions"] == 0
    assert outcome["intents"] == 0


def test_i9_data_without_i8_no_care_action(db, b15_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    outcome = _run_pipeline(db, subject, when)
    assert outcome["intents"] == 0


def test_b14_status_does_not_create_care_action(db, b15_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    with patch.dict("os.environ", {"SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true"}, clear=False):
        run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=True)
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value)
        .count()
        == 0
    )


# D scope


@pytest.mark.parametrize(
    "scope,should_notify",
    [
        (I10NotificationScope.CARE_ACTION, True),
        (I10NotificationScope.GENERAL_STATUS, False),
        (I10NotificationScope.DEVICE_STATUS, False),
        (I10NotificationScope.SAFETY_ESCALATION, False),
    ],
)
def test_scope_matrix(db, b15_patches, scope, should_notify):
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
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    count = db.query(models.Notification).filter(models.Notification.user_id == cg.id).count()
    assert (count == 1) is should_notify


# E revocation


def test_revoked_access_suppresses(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg_a.id)
        .one()
    )
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg_a.id
    )
    before = db.query(func.count(models.Notification.id)).scalar()
    outcome = process_caregiver_delivery_intent(db, intent)
    after = db.query(func.count(models.Notification.id)).scalar()
    assert outcome["status"] == "suppressed"
    assert after == before


def test_revoked_care_action_grant_suppresses(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg_a.id)
        .one()
    )
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"


# F prefs


def test_pref_on_delivers(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1


def test_pref_off_suppresses(db, b15_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_care_action=True)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == cg_a.id).update(
        {"reminder_system_enabled": False}
    )
    db.commit()
    _run_pipeline(db, subject, when)
    users = {n.user_id for n in db.query(models.Notification).all()}
    assert cg_a.id not in users
    assert cg_b.id in users


# G multi caregiver


def test_both_caregivers_independent(db, b15_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_care_action=True)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_b.id).count() == 1


def test_revoke_a_not_b(db, b15_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_care_action=True)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
    intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value)
        .all()
    )
    i_a = next(i for i in intents if i.recipient_user_id == cg_a.id)
    i_b = next(i for i in intents if i.recipient_user_id == cg_b.id)
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg_a.id
    )
    process_caregiver_delivery_intent(db, i_a)
    process_caregiver_delivery_intent(db, i_b)
    assert i_a.status == "suppressed"
    assert i_b.status == "processed"


def test_general_only_b_denied(db, b15_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_general=True)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_b.id).count() == 0


# H idempotency


def test_same_action_same_recipient_once(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    _run_pipeline(db, subject, when)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 1


def test_next_action_occurrence_allowed(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _profile_tz(db, owner.id)
    window = resolve_local_day_window(db, owner.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=owner.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{subject.id}-multi",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    refs = build_health_subject_context_refs_json(subject.id)
    for key, summary in (("act-1", "Morning routine"), ("act-2", "Evening check")):
        repo.create_action(
            db,
            user_id=owner.id,
            plan_id=plan.id,
            action_domain="routine",
            action_type="routine_care_item",
            action_idempotency_key=key,
            summary_text=summary,
            presentation_json="{}",
            knowledge_refs_json="[]",
            context_refs_json=refs,
            safety_state="SAFE",
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
        )
    db.commit()
    _run_pipeline(db, subject, when)
    assert db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count() == 2


# I completion truthfulness


def test_delivered_not_completed(db, b15_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    action = _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    db.refresh(action)
    assert action.status == "ACTIVE"


def test_copy_no_completion_claim(db, b15_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    notif = db.query(models.Notification).one()
    body = (notif.body or "").lower()
    assert "completed" not in body or "does not confirm completion" in body
    assert "failed" not in body
    assert "not done" not in body


# J/K chat


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_real_chat_continuation(mock_cmd, mock_reminder, mock_brain, db, b15_patches, monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_brain.return_value = {"message": "Ok", "language": "en"}
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    from backend.app.routers.interact import chat
    from starlette.requests import Request

    payload = ChatRequest(
        message="about the action",
        source_notification_id=notif.id,
        conversation_id="b15-conv",
    )
    scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
    resp = asyncio.run(chat(Request(scope), payload, db, cg_a))
    assert resp.continued_from_notification is True
    assert notif.health_subject_id == subject.id


def test_revoked_chat_fail_closed(db, b15_patches):
    from backend.app.services.gate4.notification_chat_context import build_safe_chat_context

    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg_a.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    ctx = build_safe_chat_context(notif, db=db, viewer_user_id=cg_a.id)
    assert ctx.get("subject_context_available") == "false"


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_cross_user_denied(mock_cmd, mock_reminder, mock_brain, db, b15_patches, monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    owner, cg_a, other, subject = _setup_caregivers(db)
    when = _when()
    _managed_action(db, owner, subject, when=when)
    _run_pipeline(db, subject, when)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    from backend.app.routers.interact import chat
    from starlette.requests import Request

    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(Request({"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}), ChatRequest(message="hi", source_notification_id=notif.id), db, other))
    assert exc.value.status_code == 403


# M transaction failure


def test_enqueue_failure_not_processed(db, b15_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    action = _managed_action(db, owner, subject, when=when)
    run_care_action_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg_a.id)
        .one()
    )
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
    db.refresh(action)
    assert action.status == "ACTIVE"


# boundaries


def test_b15_no_direct_notification_orm():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for name in (
        "care_action_producer_worker.py",
        "care_action_copy.py",
        "managed_i8_action_binding.py",
    ):
        dumped = ast.dump(ast.parse((root / name).read_text(encoding="utf-8")))
        assert "Notification(" not in dumped
        assert "NotificationBuilder" not in dumped


def test_b15_no_raw_i9():
    text = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "care_action_producer_worker.py"
    ).read_text()
    assert "PhysiologicalMeasurement" not in text


def test_b15_no_rag():
    text = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "care_action_producer_worker.py"
    ).read_text().lower()
    assert "rag_service" not in text
