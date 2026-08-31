"""I10-B09 medication adherence + canonical I10 reminder path (PostgreSQL)."""

from __future__ import annotations

import ast
import os
from datetime import datetime, time
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz
from fastapi.testclient import TestClient
from sqlalchemy import func

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.i10.medication_adherence import (
    MedicationAdherenceState,
    confirm_dose_taken_by_notification,
)
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily
from backend.app.services.medication_scheduler import process_medication_reminders
from backend.app.services.notification_engine import DecisionEngine, NotificationBuilder

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)


@pytest.fixture
def gate4_patch():
    with _GATE4_PATCH:
        yield


@pytest.fixture()
def client(db):
    """HTTP client bound to the same PostgreSQL session as the test (noconftest-safe)."""

    def _get_db_override():
        yield db

    sedi_app.dependency_overrides[_app_get_db] = _get_db_override
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)


def _user(db, name: str = "med-user") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _med_setup(db, user: models.User, *, reminder_enabled: bool = True, times: list[str] | None = None):
    med = models.Medication(name="TestMed", default_dosage="5mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    um = models.UserMedication(
        user_id=user.id,
        medication_id=med.id,
        interval_hours=8,
        user_dosage="5mg",
        reminder_enabled=reminder_enabled,
        timezone="Asia/Tehran",
    )
    db.add(um)
    db.commit()
    db.refresh(um)
    for slot in times or ["08:00"]:
        hh, mm = slot.split(":")
        db.add(
            models.UserMedicationSchedule(
                user_medication_id=um.id,
                time_of_day=time(int(hh), int(mm)),
            )
        )
    db.commit()
    return um, med


def _due_utc(hour: int, minute: int, day: int = 29) -> datetime:
    tehran = pytz.timezone("Asia/Tehran")
    local = tehran.localize(datetime(2026, 6, day, hour, minute, 0))
    return local.astimezone(pytz.UTC).replace(tzinfo=None)


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


# Schedule / I10 path


def test_schedule_creates_due_occurrence(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    now = _due_utc(8, 5)
    assert process_medication_reminders(db, DecisionEngine(db), now_utc=now) == 1
    occ = db.query(models.MedicationDoseOccurrence).filter(models.MedicationDoseOccurrence.user_id == user.id).one()
    assert occ.state == MedicationAdherenceState.DUE.value


def test_inactive_medication_no_reminder(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user, reminder_enabled=False)
    now = _due_utc(8, 5)
    assert process_medication_reminders(db, DecisionEngine(db), now_utc=now) == 0


def test_reminder_uses_i10_intake(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    now = _due_utc(8, 5)
    process_medication_reminders(db, DecisionEngine(db), now_utc=now)
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    assert notif.i10_policy_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.MEDICATION_DUE.value


def test_exactly_one_notification_per_occurrence(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    now = _due_utc(8, 5)
    engine = DecisionEngine(db)
    assert process_medication_reminders(db, engine, now_utc=now) == 1
    assert process_medication_reminders(db, engine, now_utc=now) == 0
    assert db.query(func.count(models.Notification.id)).filter(models.Notification.user_id == user.id).scalar() == 1


def test_no_parallel_legacy_persist(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    engine = DecisionEngine(db)
    with patch.object(engine.builder, "persist") as mock_legacy:
        process_medication_reminders(db, engine, now_utc=_due_utc(8, 5))
    mock_legacy.assert_not_called()


def test_no_direct_fcm(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    with patch("backend.app.services.notifications.delivery_service.FCMAdapter.send") as mock_fcm:
        process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    mock_fcm.assert_not_called()


def test_same_dose_duplicate_blocked(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    engine = DecisionEngine(db)
    now = _due_utc(8, 5)
    assert process_medication_reminders(db, engine, now_utc=now) == 1
    assert process_medication_reminders(db, engine, now_utc=now) == 0


def test_next_dose_occurrence_allowed(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user, times=["08:00", "20:00"])
    engine = DecisionEngine(db)
    assert process_medication_reminders(db, engine, now_utc=_due_utc(8, 2)) == 1
    assert process_medication_reminders(db, engine, now_utc=_due_utc(20, 3)) == 1
    assert db.query(func.count(models.Notification.id)).filter(models.Notification.user_id == user.id).scalar() == 2


def test_occurrence_keys_not_forever_static():
    from backend.app.services.i10.medication_adherence import build_medication_occurrence_key

    d1 = datetime(2026, 6, 29, 8, 0, 0)
    d2 = datetime(2026, 6, 30, 8, 0, 0)
    k1 = build_medication_occurrence_key(
        user_id=1, user_medication_id=1, schedule_id=1, scheduled_for=d1, schedule_time="08:00"
    )
    k2 = build_medication_occurrence_key(
        user_id=1, user_medication_id=1, schedule_id=1, scheduled_for=d2, schedule_time="08:00"
    )
    assert k1 != k2


# Adherence


def test_confirm_taken(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    occ = confirm_dose_taken_by_notification(db, user_id=user.id, notification_id=notif.id)
    assert occ.state == MedicationAdherenceState.CONFIRMED_TAKEN.value
    assert occ.confirmed_at is not None


def test_confirm_idempotent(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    confirm_dose_taken_by_notification(db, user_id=user.id, notification_id=notif.id)
    occ2 = confirm_dose_taken_by_notification(db, user_id=user.id, notification_id=notif.id)
    assert occ2.state == MedicationAdherenceState.CONFIRMED_TAKEN.value


def test_no_response_not_missed(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    occ = db.query(models.MedicationDoseOccurrence).filter(models.MedicationDoseOccurrence.user_id == user.id).one()
    assert occ.state == MedicationAdherenceState.DUE.value
    assert occ.state != MedicationAdherenceState.MISSED.value


def test_confirmed_blocks_repeat_reminder(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    engine = DecisionEngine(db)
    process_medication_reminders(db, engine, now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    confirm_dose_taken_by_notification(db, user_id=user.id, notification_id=notif.id)
    assert process_medication_reminders(db, engine, now_utc=_due_utc(8, 6)) == 0


# Security / API


def test_confirm_api(client: TestClient, db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    r = client.post(
        f"/notifications/{notif.id}/medication/confirm-taken",
        headers=_auth(user.id),
    )
    assert r.status_code == 200
    assert r.json()["data"]["state"] == MedicationAdherenceState.CONFIRMED_TAKEN.value


def test_cannot_confirm_other_user(db, gate4_patch):
    owner = _user(db, "owner")
    other = _user(db, "other")
    _med_setup(db, owner)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == owner.id).one()
    from backend.app.services.i10.medication_adherence import MedicationAdherenceError

    with pytest.raises(MedicationAdherenceError):
        confirm_dose_taken_by_notification(db, user_id=other.id, notification_id=notif.id)


def test_defer_does_not_mark_taken(client: TestClient, db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    client.post(
        f"/notifications/{notif.id}/feedback",
        json={"reaction": "interact", "action_id": "NOT_NOW"},
        headers=_auth(user.id),
    )
    occ = db.query(models.MedicationDoseOccurrence).filter(
        models.MedicationDoseOccurrence.source_notification_id == notif.id
    ).one()
    assert occ.state == MedicationAdherenceState.DUE.value


# Privacy / boundaries


def test_medication_privacy_class(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    assert notif.privacy_class == I10PrivacyClass.HEALTH_SENSITIVE.value


def test_self_health_subject_attribution(db, gate4_patch):
    from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account

    user = _user(db)
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    assert notif.health_subject_id == subject.id
    assert notif.user_id == user.id


def test_b09_no_rag():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for name in ("medication_adherence.py", "medication_i10_adapter.py"):
        dumped = ast.dump(ast.parse((root / name).read_text(encoding="utf-8"))).lower()
        assert "rag" not in dumped


def test_source_notification_id_linked(db, gate4_patch):
    user = _user(db)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc(8, 5))
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    occ = db.query(models.MedicationDoseOccurrence).one()
    assert occ.source_notification_id == notif.id
