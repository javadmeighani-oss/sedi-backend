"""Gate 2 V1 — profile persistence via PATCH/GET /auth/me."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc


def _access_token_for_phone(client, db, monkeypatch, phone: str, code: str = "123456") -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_gate2_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value=code):
        ok, _, _ = svc.request_otp(db, phone)
    assert ok is True
    verify = client.post("/auth/otp/verify", json={"phone": phone, "code": code})
    assert verify.status_code == 200 and verify.json().get("ok") is True
    return verify.json()["data"]["access_token"]


def test_patch_gate2_new_user_profile_fields(client, db, monkeypatch):
    phone = "+989131001001"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    patch_body = {
        "name": "Sara Ahmadi",
        "sex": "female",
        "preferred_language": "fa",
        "calendar_type": "jalali",
        "birth_day": 15,
        "birth_month": 1,
        "birth_year": 1370,
        "date_of_birth": "1991-04-04",
    }
    r = client.patch(
        "/auth/me",
        json=patch_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Sara Ahmadi"
    assert data["sex"] == "female"
    assert data["preferred_language"] == "fa"
    assert data["calendar_type"] == "jalali"
    assert data["birth_day"] == 15
    assert data["birth_month"] == 1
    assert data["birth_year"] == 1370
    assert data["date_of_birth"] == "1991-04-04"
    assert data["phone"] == phone

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    me_data = me.json()["data"]
    assert me_data["name"] == "Sara Ahmadi"
    assert me_data["calendar_type"] == "jalali"
    assert me_data["birth_year"] == 1370


def test_patch_gate2_rejects_invalid_sex(client, db, monkeypatch):
    phone = "+989131001002"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"sex": "unknown_gender"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_patch_gate2_gregorian_birth_year(client, db, monkeypatch):
    phone = "+989131001003"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={
            "name": "John",
            "calendar_type": "gregorian",
            "birth_day": 1,
            "birth_month": 1,
            "birth_year": 1990,
            "date_of_birth": "1990-01-01",
            "sex": "male",
            "preferred_language": "en",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["calendar_type"] == "gregorian"
    assert data["birth_year"] == 1990
    assert data["date_of_birth"] == "1990-01-01"
