"""Phase V1.1B — user medication API and scheduled reminders."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from unittest.mock import patch

import pytest
import pytz
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["SMS_DISABLED"] = "true"

from backend.app.core.security import create_access_token
from backend.app.models import Medication, Notification, User, UserMedication, UserMedicationSchedule
from backend.app.services import auth_otp_service as svc
from backend.app.services.medication_scheduler import process_medication_reminders
from backend.app.services.notification_engine import DecisionEngine

NOTIFICATION_TYPE_HEALTH_ALERT = "health_alert"


def _access_token_for_phone(client: TestClient, db, monkeypatch, phone: str, code: str = "123456") -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_secret_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value=code):
        ok, _, _ = svc.request_otp(db, phone)
    assert ok is True
    verify = client.post("/auth/verify_otp", json={"phone": phone, "code": code})
    assert verify.status_code == 200 and verify.json().get("ok") is True
    return verify.json()["data"]["access_token"]


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_body(**overrides) -> dict:
    body = {
        "name": "Metformin",
        "user_dosage": "500mg",
        "dosage_form": "tablet",
        "instructions": "After meal",
        "reminder_enabled": True,
        "timezone": "Asia/Tehran",
        "reminder_times": ["08:00", "20:00"],
    }
    body.update(overrides)
    return body


# --- API auth / CRUD ---


def test_user_medications_requires_auth(client: TestClient):
    assert client.get("/user/medications").status_code == 401
    assert client.post("/user/medications", json=_create_body()).status_code == 401
    assert client.patch("/user/medications/1", json={"user_dosage": "250mg"}).status_code == 401
    assert client.delete("/user/medications/1").status_code == 401


def test_create_medication_with_reminder_times(client: TestClient, db, monkeypatch):
    phone = "+989141111111"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.post(
        "/user/medications",
        json=_create_body(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data", {})
    assert data.get("name") == "Metformin"
    assert data.get("user_dosage") == "500mg"
    assert set(data.get("reminder_times", [])) == {"08:00", "20:00"}


def test_list_own_medications(client: TestClient, db, monkeypatch):
    phone = "+989142222222"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    client.post(
        "/user/medications",
        json=_create_body(name="Aspirin", reminder_times=["09:00"]),
        headers={"Authorization": f"Bearer {token}"},
    )
    r = client.get("/user/medications", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    meds = r.json().get("data", {}).get("medications", [])
    assert len(meds) == 1
    assert meds[0]["name"] == "Aspirin"
    assert meds[0]["reminder_times"] == ["09:00"]


def test_duplicate_assignment_rejected(client: TestClient, db, monkeypatch):
    phone = "+989143333333"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/user/medications", json=_create_body(), headers=headers).status_code == 200
    dup = client.post("/user/medications", json=_create_body(), headers=headers)
    assert dup.status_code == 200
    assert dup.json().get("ok") is False
    assert dup.json().get("error", {}).get("code") == "MEDICATION_ALREADY_ASSIGNED"


def test_cross_user_list_isolation(client: TestClient, db, monkeypatch):
    token_a = _access_token_for_phone(client, db, monkeypatch, "+989144444441")
    token_b = _access_token_for_phone(client, db, monkeypatch, "+989144444442")
    client.post(
        "/user/medications",
        json=_create_body(name="PrivateMed"),
        headers={"Authorization": f"Bearer {token_a}"},
    )
    r_b = client.get("/user/medications", headers={"Authorization": f"Bearer {token_b}"})
    assert r_b.status_code == 200
    assert r_b.json().get("data", {}).get("medications", []) == []


def test_cross_user_patch_returns_404(client: TestClient, db, monkeypatch):
    token_a = _access_token_for_phone(client, db, monkeypatch, "+989145555551")
    token_b = _access_token_for_phone(client, db, monkeypatch, "+989145555552")
    created = client.post(
        "/user/medications",
        json=_create_body(),
        headers={"Authorization": f"Bearer {token_a}"},
    )
    um_id = created.json()["data"]["id"]
    r = client.patch(
        f"/user/medications/{um_id}",
        json={"user_dosage": "Hacked"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


def test_cross_user_delete_returns_404(client: TestClient, db, monkeypatch):
    token_a = _access_token_for_phone(client, db, monkeypatch, "+989146666661")
    token_b = _access_token_for_phone(client, db, monkeypatch, "+989146666662")
    created = client.post(
        "/user/medications",
        json=_create_body(),
        headers={"Authorization": f"Bearer {token_a}"},
    )
    um_id = created.json()["data"]["id"]
    assert client.delete(
        f"/user/medications/{um_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    ).status_code == 404


def test_patch_updates_user_fields_not_shared_medication_for_other_user(
    client: TestClient, db, monkeypatch
):
    token_a = _access_token_for_phone(client, db, monkeypatch, "+989147777771")
    token_b = _access_token_for_phone(client, db, monkeypatch, "+989147777772")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    id_a = client.post("/user/medications", json=_create_body(user_dosage="500mg"), headers=headers_a).json()["data"]["id"]
    id_b = client.post("/user/medications", json=_create_body(user_dosage="250mg"), headers=headers_b).json()["data"]["id"]

    client.patch(f"/user/medications/{id_a}", json={"user_dosage": "750mg"}, headers=headers_a)

    med_b = client.get("/user/medications", headers=headers_b).json()["data"]["medications"][0]
    assert med_b["user_dosage"] == "250mg"
    med_a = client.get("/user/medications", headers=headers_a).json()["data"]["medications"][0]
    assert med_a["user_dosage"] == "750mg"


def test_delete_removes_assignment(client: TestClient, db, monkeypatch):
    phone = "+989148888888"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    um_id = client.post("/user/medications", json=_create_body(), headers=headers).json()["data"]["id"]
    assert client.delete(f"/user/medications/{um_id}", headers=headers).status_code == 200
    assert client.get("/user/medications", headers=headers).json()["data"]["medications"] == []


def test_rejects_user_id_in_body(client: TestClient, db, monkeypatch):
    phone = "+989149999999"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    body = _create_body()
    body["user_id"] = 99999
    assert client.post(
        "/user/medications",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 422


def test_post_rejects_user_id_query(client: TestClient, db, monkeypatch):
    phone = "+989141010101"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.post(
        "/user/medications?user_id=123",
        json=_create_body(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_patch_rejects_user_id_query(client: TestClient, db, monkeypatch):
    phone = "+989141020202"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    um_id = client.post("/user/medications", json=_create_body(), headers=headers).json()["data"]["id"]
    r = client.patch(
        f"/user/medications/{um_id}?user_id=123",
        json={"user_dosage": "250mg"},
        headers=headers,
    )
    assert r.status_code == 422


def test_delete_rejects_user_id_query(client: TestClient, db, monkeypatch):
    phone = "+989141030303"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    um_id = client.post("/user/medications", json=_create_body(), headers=headers).json()["data"]["id"]
    r = client.delete(f"/user/medications/{um_id}?user_id=123", headers=headers)
    assert r.status_code == 422


# --- Scheduler ---


def _setup_scheduled_medication(db: Session, user: User, times: list[str]) -> UserMedication:
    med = Medication(name="SchedulerMed", default_dosage=None)
    db.add(med)
    db.commit()
    db.refresh(med)
    um = UserMedication(
        user_id=user.id,
        medication_id=med.id,
        interval_hours=8,
        user_dosage="10mg",
        reminder_enabled=True,
        timezone="Asia/Tehran",
    )
    db.add(um)
    db.commit()
    db.refresh(um)
    for t in times:
        hh, mm = t.split(":")
        db.add(
            UserMedicationSchedule(
                user_medication_id=um.id,
                time_of_day=time(int(hh), int(mm)),
            )
        )
    db.commit()
    return um


def test_scheduler_creates_reminder_when_schedule_due(db: Session):
    user = User(name="SchedUser", secret_key="k", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    _setup_scheduled_medication(db, user, ["08:00"])

    tehran = pytz.timezone("Asia/Tehran")
    local_due = tehran.localize(datetime(2026, 6, 29, 8, 5, 0))
    now_utc = local_due.astimezone(pytz.UTC).replace(tzinfo=None)

    engine = DecisionEngine(db)
    created = process_medication_reminders(db, engine, now_utc=now_utc)
    assert created == 1

    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.type == NOTIFICATION_TYPE_HEALTH_ALERT)
        .all()
    )
    assert len(rows) >= 1
    assert "SchedulerMed" in (rows[0].body or "")


def test_scheduler_no_duplicate_for_same_time_window(db: Session):
    user = User(name="DedupeUser", secret_key="k", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    _setup_scheduled_medication(db, user, ["08:00"])

    tehran = pytz.timezone("Asia/Tehran")
    local_due = tehran.localize(datetime(2026, 6, 29, 8, 7, 0))
    now_utc = local_due.astimezone(pytz.UTC).replace(tzinfo=None)

    engine = DecisionEngine(db)
    assert process_medication_reminders(db, engine, now_utc=now_utc) == 1
    assert process_medication_reminders(db, engine, now_utc=now_utc) == 0


def test_scheduler_multiple_times_per_medication(db: Session):
    user = User(name="MultiTimeUser", secret_key="k", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    _setup_scheduled_medication(db, user, ["08:00", "20:00"])

    tehran = pytz.timezone("Asia/Tehran")
    morning = tehran.localize(datetime(2026, 6, 29, 8, 2, 0)).astimezone(pytz.UTC).replace(tzinfo=None)
    evening = tehran.localize(datetime(2026, 6, 29, 20, 3, 0)).astimezone(pytz.UTC).replace(tzinfo=None)

    engine = DecisionEngine(db)
    assert process_medication_reminders(db, engine, now_utc=morning) == 1
    assert process_medication_reminders(db, engine, now_utc=evening) == 1


def test_scheduler_legacy_without_schedule_backward_compatible(db: Session):
    user = User(name="LegacyUser", secret_key="k", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    med = Medication(name="LegacyMed", default_dosage="5mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    um = UserMedication(user_id=user.id, medication_id=med.id, interval_hours=8, reminder_enabled=True)
    db.add(um)
    db.commit()

    engine = DecisionEngine(db)
    created = process_medication_reminders(db, engine)
    assert created == 1
    assert process_medication_reminders(db, engine) == 0


def test_delete_stops_scheduler_reminders(client: TestClient, db, monkeypatch):
    phone = "+989140000000"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    um_id = client.post(
        "/user/medications",
        json=_create_body(name="ToDelete", reminder_times=["08:00"]),
        headers=headers,
    ).json()["data"]["id"]
    user = db.query(User).filter(User.phone == phone).first()
    client.delete(f"/user/medications/{um_id}", headers=headers)

    tehran = pytz.timezone("Asia/Tehran")
    now_utc = tehran.localize(datetime(2026, 6, 29, 8, 4, 0)).astimezone(pytz.UTC).replace(tzinfo=None)
    engine = DecisionEngine(db)
    assert process_medication_reminders(db, engine, now_utc=now_utc) == 0
    assert db.query(UserMedication).filter(UserMedication.user_id == user.id).count() == 0
