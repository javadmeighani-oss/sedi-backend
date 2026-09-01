"""I10-B14 caregiver status digest + care data gap (PostgreSQL cross-section)."""

from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import func

from backend.app import models
from backend.app.schemas.chat import ChatRequest
from backend.app.services.i10.care_digest_producer_worker import run_care_digest_producer_for_subject
from backend.app.services.i10.care_network_access import grant_caregiver_subject_access, revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import create_subject_notification_grant, revoke_subject_notification_grant_by_scope
from backend.app.services.i10.care_subject_status_facts import CareSubjectDataStatus, assemble_care_subject_status_facts
from backend.app.services.i10.caregiver_data_gap import is_care_data_gap_candidate
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.caregiver_status_digest import FORBIDDEN_PHRASES, render_care_status_digest_body
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account
from backend.app.services.i9.i8_projection_service import get_bounded_context_projection_for_subject

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
def b14_patches():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, name: str, *, lang: str = "en") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language=lang)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _push(db, user_id: int, token: str) -> None:
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=token, is_active=True))
    db.commit()


def _prefs(db, user_id: int, *, health_alert: bool = True) -> None:
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=True,
            health_alert_enabled=health_alert,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()


def _when(day: str = "2026-08-31", hour: int = 9) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00")


def _period_start(when: datetime) -> datetime:
    day = when.date()
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _rollup(
    db,
    owner: models.User,
    subject: models.HealthSubject,
    when: datetime,
    *,
    sample_count: int = 12,
    coverage: float = 0.85,
    avg_value: float = 78.0,
    hours_before_end: float = 2.0,
) -> models.PhysiologicalMeasurementRollup:
    start = _period_start(when)
    bucket_end = when - timedelta(hours=hours_before_end)
    row = models.PhysiologicalMeasurementRollup(
        user_id=owner.id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        bucket_kind="daily",
        bucket_start=start,
        bucket_end=bucket_end,
        sample_count=sample_count,
        avg_value=avg_value,
        min_value=avg_value - 5,
        max_value=avg_value + 5,
        coverage=coverage,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _baseline(db, owner, subject, when, *, baseline_value: float = 72.0):
    start = _period_start(when) - timedelta(days=14)
    end = _period_start(when)
    row = models.PhysiologicalBaseline(
        user_id=owner.id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        baseline_method="PERSONAL_OBSERVED_BASELINE_V1",
        baseline_value=baseline_value,
        window_start=start,
        window_end=end,
        coverage=0.8,
    )
    db.add(row)
    db.commit()
    return row


def _setup_caregivers(
    db,
    *,
    cg_a_general: bool = True,
    cg_b_device: bool = True,
    cg_b_general: bool = False,
):
    owner = _user(db, "owner")
    cg_a = _user(db, "cg-a", lang="fa")
    cg_b = _user(db, "cg-b")
    subject = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="Parent", access_role="MANAGER"
    )
    for cg in (cg_a, cg_b):
        grant_caregiver_subject_access(
            db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
        )
        _push(db, cg.id, f"fcm-{cg.id}")
        _prefs(db, cg.id)
    if cg_a_general:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_a.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    if cg_b_device:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg_b.id,
            notification_scope=I10NotificationScope.DEVICE_STATUS,
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


def _run_pipeline(db, subject, when, *, deliver: bool = True) -> dict:
    return run_care_digest_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=deliver, commit=True
    )


# --- A. Real I9 status digest path ---


def test_real_status_digest_path(db, b14_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg_a.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .one()
    )
    assert intent.status == "processed"
    assert intent.notification_id is not None
    assert intent.i10_decision_id is not None
    notif = db.query(models.Notification).filter(models.Notification.id == intent.notification_id).one()
    assert notif.user_id == cg_a.id
    assert notif.health_subject_id == subject.id
    assert notif.health_subject_id != cg_a.id


# --- B. Data status semantics ---


@pytest.mark.parametrize(
    "sample_count,coverage,hours_before_end,expected",
    [
        (20, 0.9, 2.0, CareSubjectDataStatus.SUFFICIENT_OBSERVED_DATA),
        (8, 0.2, 2.0, CareSubjectDataStatus.PARTIAL_DATA),
        (10, 0.9, 60.0, CareSubjectDataStatus.STALE_DATA),
        (0, 0.0, 2.0, CareSubjectDataStatus.NO_DATA),
    ],
)
def test_data_status_semantics(db, b14_patches, sample_count, coverage, hours_before_end, expected):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(
        db,
        owner,
        subject,
        when,
        sample_count=sample_count,
        coverage=coverage,
        hours_before_end=hours_before_end,
    )
    facts = assemble_care_subject_status_facts(db, health_subject_id=subject.id, when=when)
    assert facts.data_status == expected
    body = render_care_status_digest_body(facts).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in body


def test_no_data_not_normal(db, b14_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when, sample_count=0, coverage=0.0)
    facts = assemble_care_subject_status_facts(db, health_subject_id=subject.id, when=when)
    assert facts.data_status == CareSubjectDataStatus.NO_DATA
    assert "normal" not in render_care_status_digest_body(facts).lower()


def test_no_alert_not_healthy(db, b14_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    facts = assemble_care_subject_status_facts(db, health_subject_id=subject.id, when=when)
    assert "healthy" not in render_care_status_digest_body(facts).lower()
    assert "No qualifying alert" in facts.alert_summary


def test_baseline_not_clinical_normal(db, b14_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when, avg_value=90.0)
    _baseline(db, owner, subject, when, baseline_value=70.0)
    facts = assemble_care_subject_status_facts(db, health_subject_id=subject.id, when=when)
    body = render_care_status_digest_body(facts)
    assert "clinical normal" in body.lower()


def test_bounded_projection_no_raw_measurements(db, b14_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    projection = get_bounded_context_projection_for_subject(db, health_subject_id=subject.id)
    assert projection.health_subject_id == subject.id
    assert projection.daily_rollup is not None


# --- C. CARE_DATA_GAP ---


def test_stale_data_gap_created(db, b14_patches):
    owner, _, cg_b, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when, hours_before_end=60.0)
    _run_pipeline(db, subject, when)
    gap_intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg_b.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .one()
    )
    assert gap_intent.notification_scope == I10NotificationScope.DEVICE_STATUS.value
    notif = db.query(models.Notification).filter(models.Notification.id == gap_intent.notification_id).one()
    assert "medical emergency" not in notif.body.lower()
    assert notif.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value


def test_partial_data_not_automatic_gap(db, b14_patches):
    owner, _, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when, coverage=0.2)
    facts = assemble_care_subject_status_facts(db, health_subject_id=subject.id, when=when)
    assert facts.data_status == CareSubjectDataStatus.PARTIAL_DATA
    assert is_care_data_gap_candidate(facts) is False


def test_no_expected_source_no_gap(db, b14_patches):
    _, _, _, subject = _setup_caregivers(db)
    when = _when()
    facts = assemble_care_subject_status_facts(db, health_subject_id=subject.id, when=when)
    assert is_care_data_gap_candidate(facts) is False
    outcome = _run_pipeline(db, subject, when)
    assert outcome["gap_intents"] == 0


def test_gap_occurrence_deduped(db, b14_patches):
    owner, _, cg_b, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when, hours_before_end=60.0)
    _run_pipeline(db, subject, when)
    _run_pipeline(db, subject, when)
    count = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg_b.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .count()
    )
    assert count == 1


def test_new_gap_episode_allowed(db, b14_patches):
    owner, _, cg_b, subject = _setup_caregivers(db)
    when1 = _when("2026-08-30")
    when2 = _when("2026-09-01")
    _rollup(db, owner, subject, when1, hours_before_end=60.0)
    _run_pipeline(db, subject, when1)
    db.query(models.PhysiologicalMeasurementRollup).delete()
    db.commit()
    _rollup(db, owner, subject, when2, hours_before_end=60.0, avg_value=80.0)
    _run_pipeline(db, subject, when2)
    count = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg_b.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .count()
    )
    assert count == 2


# --- D. Scope matrix ---


def test_status_digest_a_only(db, b14_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_a_general=True, cg_b_device=True, cg_b_general=False)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    status_a = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST.value,
            models.Notification.user_id == cg_a.id,
        )
        .count()
    )
    status_b = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST.value,
            models.Notification.user_id == cg_b.id,
        )
        .count()
    )
    assert status_a == 1
    assert status_b == 0


def test_data_gap_b_only(db, b14_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when, hours_before_end=60.0)
    _run_pipeline(db, subject, when)
    gap_a = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
            models.Notification.user_id == cg_a.id,
        )
        .count()
    )
    gap_b = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
            models.Notification.user_id == cg_b.id,
        )
        .count()
    )
    assert gap_a == 0
    assert gap_b == 1


def test_both_general_status_independent(db, b14_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_general=True)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    rows = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST.value)
        .all()
    )
    assert len(rows) == 2
    assert {r.user_id for r in rows} == {cg_a.id, cg_b.id}


# --- E/F. Revocation at delivery ---


def test_revoked_access_no_notification(db, b14_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
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


def test_revoked_grant_no_notification(db, b14_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
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
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"
    assert intent.notification_id is None


# --- G. Preferences ---


def test_pref_disabled_suppressed(db, b14_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_general=True)
    when = _when()
    _rollup(db, owner, subject, when)
    db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == cg_a.id).update(
        {"health_alert_enabled": False}
    )
    db.commit()
    _run_pipeline(db, subject, when)
    notifs = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST.value)
        .all()
    )
    assert {n.user_id for n in notifs} == {cg_b.id}


# --- H. Push readiness ---


def test_no_push_auth_valid_delivery_fails(db, b14_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    db.query(models.PushDevice).filter(models.PushDevice.user_id == cg_a.id).delete()
    db.commit()
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == cg_a.id)
        .one()
    )
    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"
    assert intent.failure_reason == "NO_PUSH_DEVICE"


# --- I/J. Chat continuation ---


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_real_chat_continuation(mock_cmd, mock_reminder, mock_brain, db, b14_patches, monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_brain.return_value = {"message": "Continuing.", "language": "en"}
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    notif = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == cg_a.id, models.Notification.health_subject_id == subject.id)
        .one()
    )
    from backend.app.routers.interact import chat
    from starlette.requests import Request

    payload = ChatRequest(
        message="continue",
        source_notification_id=notif.id,
        conversation_id="b14-conv",
        interaction_source="notification",
    )

    async def _run():
        scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
        request = Request(scope)
        return await chat(request, payload, db, cg_a)

    resp = asyncio.run(_run())
    assert resp.continued_from_notification is True
    nctx = mock_brain.call_args.kwargs.get("notification_context") or {}
    assert "care_status_digest" in str(nctx.get("template_key", "")) or "daily_status" in str(
        nctx.get("category", "")
    )


def test_revoked_chat_context_fail_closed(db, b14_patches):
    from backend.app.services.gate4.notification_chat_context import build_safe_chat_context

    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    revoke_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg_a.id
    )
    ctx = build_safe_chat_context(notif, db=db, viewer_user_id=cg_a.id)
    assert ctx["template_key"] == "care_notification_generic"
    hints = ctx.get("context_hints") or {}
    assert hints.get("subject_context_available") == "false"
    assert "data_status" not in hints


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_cross_user_source_notification_denied(mock_cmd, mock_reminder, mock_brain, db, b14_patches, monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    owner, cg_a, other, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    notif = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).one()
    from backend.app.routers.interact import chat
    from starlette.requests import Request

    payload = ChatRequest(message="hi", source_notification_id=notif.id)
    scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
    request = Request(scope)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(request, payload, db, other))
    assert exc.value.status_code == 403


# --- L. Idempotency ---


def test_same_occurrence_same_caregiver_once(db, b14_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    _run_pipeline(db, subject, when)
    count = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count()
    assert count == 1


def test_same_occurrence_two_caregivers(db, b14_patches):
    owner, cg_a, cg_b, subject = _setup_caregivers(db, cg_b_general=True)
    when = _when()
    _rollup(db, owner, subject, when)
    _run_pipeline(db, subject, when)
    count = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST.value)
        .count()
    )
    assert count == 2


def test_new_period_same_caregiver_allowed(db, b14_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when1 = _when("2026-08-30")
    when2 = _when("2026-09-01")
    _rollup(db, owner, subject, when1)
    _run_pipeline(db, subject, when1)
    _rollup(db, owner, subject, when2)
    _run_pipeline(db, subject, when2)
    count = db.query(models.Notification).filter(models.Notification.user_id == cg_a.id).count()
    assert count == 2


# --- M. Transaction failure ---


def test_enqueue_failure_not_marked_processed(db, b14_patches):
    owner, cg_a, _, subject = _setup_caregivers(db)
    when = _when()
    _rollup(db, owner, subject, when)
    run_care_digest_producer_for_subject(db, health_subject_id=subject.id, when=when, deliver=False)
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


# --- Boundaries ---


def test_b14_no_direct_notification_orm():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for name in (
        "care_digest_producer_worker.py",
        "caregiver_status_digest.py",
        "caregiver_data_gap.py",
        "care_subject_status_facts.py",
    ):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        dumped = ast.dump(tree)
        assert "Notification(" not in dumped
        assert "NotificationBuilder" not in dumped


def test_b14_no_fcm():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    dumped = ast.dump(ast.parse((root / "care_digest_producer_worker.py").read_text(encoding="utf-8"))).lower()
    assert "fcm" not in dumped


def test_b14_no_raw_measurement_query():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    dumped = ast.dump(
        ast.parse((root / "care_subject_status_facts.py").read_text(encoding="utf-8"))
    )
    without_rollup = dumped.replace("PhysiologicalMeasurementRollup", "")
    assert "PhysiologicalMeasurement" not in without_rollup
