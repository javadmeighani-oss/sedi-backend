"""Gate 1 — device subject_user_id for dependents."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.models import Device
from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_device_defaults_subject_to_owner(client, db, monkeypatch):
    phone = "+989145005001"
    token = _token(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/devices/register",
        json={"device_id": "Gate1Dev001"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    subj = r.json()["data"]["subject_user_id"]
    user = db.query(Device).filter(Device.device_id == "Gate1Dev001").first()
    assert user.subject_user_id == user.user_id
    assert subj == user.user_id


def test_caregiver_registers_device_for_dependent(client, db, monkeypatch):
    phone = "+989145005002"
    token = _token(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    dep_id = client.post(
        "/user/dependents",
        json={"name": "Dependent Patient"},
        headers=headers,
    ).json()["data"]["dependent_user_id"]

    r = client.post(
        "/devices/register",
        json={"device_id": "Gate1DepDev", "subject_user_id": dep_id},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["data"]["subject_user_id"] == dep_id

    dev = db.query(Device).filter(Device.device_id == "Gate1DepDev").first()
    assert dev.subject_user_id == dep_id


def test_caregiver_cannot_register_for_unrelated_user(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989145005003")
    t2 = _token(client, db, monkeypatch, "+989145005004")
    dep_id = client.post(
        "/user/dependents",
        json={"name": "Private Dep"},
        headers={"Authorization": f"Bearer {t1}"},
    ).json()["data"]["dependent_user_id"]
    r = client.post(
        "/devices/register",
        json={"device_id": "Gate1HackDev", "subject_user_id": dep_id},
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"]["code"] == "DEVICE_SUBJECT_FORBIDDEN"
