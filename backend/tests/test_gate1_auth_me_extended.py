"""Gate 1 — extended GET/PATCH /auth/me."""

import os
from datetime import date
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"})
    return r.json()["data"]["access_token"]


def test_auth_me_includes_gate1_fields(client, db, monkeypatch):
    phone = "+989141001001"
    token = _token(client, db, monkeypatch, phone)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data.get("account_type") == "normal"
    assert "timezone" in data
    assert "date_of_birth" in data
    assert "height_cm" in data
    assert "weight_kg" in data


def test_patch_extended_profile_fields(client, db, monkeypatch):
    phone = "+989141001002"
    token = _token(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={
            "timezone": "Asia/Tehran",
            "date_of_birth": "1985-06-15",
            "height_cm": 175,
            "weight_kg": 72.5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["timezone"] == "Asia/Tehran"
    assert data["birth_year"] == 1985
    assert data["height_cm"] == 175


def test_patch_rejects_invalid_timezone(client, db, monkeypatch):
    phone = "+989141001003"
    token = _token(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"timezone": "Not/A/Real/Zone"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_patch_rejects_user_id_in_body(client, db, monkeypatch):
    phone = "+989141001004"
    token = _token(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"name": "X", "user_id": 999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
