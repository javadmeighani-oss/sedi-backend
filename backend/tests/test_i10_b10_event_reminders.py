"""I10-B10 medical event reminders — doctor/lab/other via canonical I10 (PostgreSQL)."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz
from sqlalchemy import func

from backend.app import models
from backend.app.services.i10.event_reminder_i10_adapter import (
    DOCTOR_EVENT_TYPE,
    LAB_EVENT_TYPE,
    build_event_occurrence_key,
    evaluate_post_event_follow_up_eligible,
    resolve_event_semantic_family,
)
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.section10.event_reminder_scheduler import process_event_reminders

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch(
    "backend.app.services.section10.feature_flags.event_reminder_scheduler_enabled",
    return_value=True,
)


@pytest.fixture
def gate4_patch():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, name: str = "evt-user") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    ensure_self_subject_for_account(db, row.id, commit=True)
    return row


def _event(
    db,
    user: models.User,
    *,
    event_type: str = DOCTOR_EVENT_TYPE,
    title: str = "Dr Visit",
    starts_in_min: int = 60,
    offsets: list[int] | None = None,
    reminder_enabled: bool = True,
    status: str = "scheduled",
    event_domain: str = "medical",
) -> models.UserEvent:
    now = datetime.utcnow()
    starts = now + timedelta(minutes=starts_in_min)
    ev = models.UserEvent(
        user_id=user.id,
        title=title,
        event_type=event_type,
        event_domain=event_domain,
        starts_at=starts,
        timezone="UTC",
        status=status,
        reminder_enabled=reminder_enabled,
        reminder_offsets_json=json.dumps(offsets or [60]),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def test_doctor_visit_recognized(gate4_patch, db):
    user = _user(db)
    ev = _event(db, user, event_type=DOCTOR_EVENT_TYPE)
    assert resolve_event_semantic_family(ev.event_type) == I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER


def test_lab_test_recognized(gate4_patch, db):
    user = _user(db)
    ev = _event(db, user, event_type=LAB_EVENT_TYPE, title="Blood work")
    assert resolve_event_semantic_family(ev.event_type) == I10SemanticFamily.LAB_APPOINTMENT_REMINDER


def test_non_medical_event_skipped(gate4_patch, db):
    user = _user(db)
    _event(db, user, event_type="birthday", event_domain="personal", title="Party")
    assert process_event_reminders(db) == 0


def test_doctor_reminder_routes_i10(gate4_patch, db):
    user = _user(db)
    _event(db, user, event_type=DOCTOR_EVENT_TYPE)
    assert process_event_reminders(db) == 1
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    assert notif.i10_policy_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER.value


def test_lab_reminder_routes_i10(gate4_patch, db):
    user = _user(db)
    _event(db, user, event_type=LAB_EVENT_TYPE, title="CBC")
    assert process_event_reminders(db) == 1
    notif = db.query(models.Notification).one()
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.LAB_APPOINTMENT_REMINDER.value
    assert "lab" in notif.body.lower()


def test_exactly_one_notification_per_stage(gate4_patch, db):
    user = _user(db)
    _event(db, user)
    process_event_reminders(db)
    count = db.query(func.count(models.Notification.id)).scalar()
    assert count == 1


def test_no_direct_orm_legacy_write(gate4_patch, db):
    sched = Path(__file__).resolve().parents[1] / "app" / "services" / "section10" / "event_reminder_scheduler.py"
    assert "models.Notification(" not in sched.read_text(encoding="utf-8")


def test_no_direct_fcm(gate4_patch, db):
    user = _user(db)
    _event(db, user)
    with patch("backend.app.services.notifications.delivery_service.FCMAdapter.send") as mock_fcm:
        process_event_reminders(db)
    mock_fcm.assert_not_called()


def test_same_event_stage_duplicate_blocked(gate4_patch, db):
    user = _user(db)
    _event(db, user)
    assert process_event_reminders(db) == 1
    assert process_event_reminders(db) == 0


def test_different_stage_allowed(gate4_patch, db):
    user = _user(db)
    base = datetime.utcnow()
    starts = base + timedelta(minutes=90)
    ev = models.UserEvent(
        user_id=user.id,
        title="Staged",
        event_type=DOCTOR_EVENT_TYPE,
        event_domain="medical",
        starts_at=starts,
        timezone="UTC",
        status="scheduled",
        reminder_enabled=True,
        reminder_offsets_json=json.dumps([30, 60]),
    )
    db.add(ev)
    db.commit()
    c1 = process_event_reminders(db, now=base + timedelta(minutes=55))
    c2 = process_event_reminders(db, now=base + timedelta(minutes=65))
    assert c1 >= 1
    assert c2 >= 1
    assert db.query(func.count(models.Notification.id)).scalar() >= 2


def test_different_event_allowed(gate4_patch, db):
    user = _user(db)
    _event(db, user, title="Visit A")
    _event(db, user, title="Visit B", starts_in_min=90)
    assert process_event_reminders(db) == 2


def test_occurrence_keys_not_forever_static():
    k1 = build_event_occurrence_key(user_id=1, event_id=1, offset_min=60)
    k2 = build_event_occurrence_key(user_id=1, event_id=2, offset_min=60)
    assert k1 != k2


def test_no_automatic_attendance_or_missed(gate4_patch, db):
    user = _user(db)
    ev = _event(db, user)
    process_event_reminders(db)
    db.refresh(ev)
    assert ev.status == "scheduled"


def test_post_event_follow_up_eligible_without_attendance_assertion(db):
    user = _user(db)
    past = datetime.utcnow() - timedelta(hours=2)
    ev = models.UserEvent(
        user_id=user.id,
        title="Past visit",
        event_type=DOCTOR_EVENT_TYPE,
        event_domain="medical",
        starts_at=past,
        ends_at=past + timedelta(hours=1),
        status="scheduled",
        reminder_enabled=False,
    )
    db.add(ev)
    db.commit()
    assert evaluate_post_event_follow_up_eligible(ev, datetime.utcnow()) is True
    assert "attended" not in (ev.status or "").lower()


def test_privacy_class_health_sensitive(gate4_patch, db):
    user = _user(db)
    _event(db, user)
    process_event_reminders(db)
    notif = db.query(models.Notification).one()
    assert notif.privacy_class == I10PrivacyClass.HEALTH_SENSITIVE.value


def test_source_notification_id_compatible(gate4_patch, db):
    user = _user(db)
    _event(db, user)
    process_event_reminders(db)
    notif = db.query(models.Notification).one()
    assert notif.id is not None
    assert notif.user_id == user.id


def test_cross_user_event_isolation(gate4_patch, db):
    u1 = _user(db, "u1")
    u2 = _user(db, "u2")
    _event(db, u1)
    assert process_event_reminders(db) == 1
    notif = db.query(models.Notification).one()
    assert notif.user_id == u1.id
    assert notif.user_id != u2.id


def test_b10_no_rag_in_adapter():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "event_reminder_i10_adapter.py"
    dumped = ast.dump(ast.parse(root.read_text(encoding="utf-8"))).lower()
    assert "rag" not in dumped


def test_flag_off_no_processing(db):
    user = _user(db)
    _event(db, user)
    with patch(
        "backend.app.services.section10.feature_flags.event_reminder_scheduler_enabled",
        return_value=False,
    ):
        assert process_event_reminders(db) == 0


def test_other_medical_event_semantic(gate4_patch, db):
    user = _user(db)
    _event(db, user, event_type="imaging", title="MRI")
    process_event_reminders(db)
    decision = db.query(models.I10NotificationDecision).one()
    assert decision.semantic_family == I10SemanticFamily.MEDICAL_EVENT_REMINDER.value
