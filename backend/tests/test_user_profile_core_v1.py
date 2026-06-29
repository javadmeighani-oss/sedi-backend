"""Phase V1.1A — unified profile core via GET/PATCH /auth/me."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

import pytest
from fastapi.testclient import TestClient

from backend.app import models
from backend.app.services import auth_otp_service as svc


def _access_token_for_phone(client: TestClient, db, monkeypatch, phone: str, code: str = "123456") -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_secret_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value=code):
        ok, _, _ = svc.request_otp(db, phone)
    assert ok is True
    verify = client.post("/auth/verify_otp", json={"phone": phone, "code": code})
    assert verify.status_code == 200 and verify.json().get("ok") is True
    return verify.json()["data"]["access_token"]


def test_get_auth_me_requires_auth(client: TestClient):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_patch_profile_core_fields_persist(client: TestClient, db, monkeypatch):
    phone = "+989131111111"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={
            "birth_year": 1990,
            "sex": "female",
            "addressing_preference": "formal",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data", {})
    assert data.get("birth_year") == 1990
    assert data.get("sex") == "female"
    assert data.get("addressing_preference") == "formal"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    me_data = me.json().get("data", {})
    assert me_data.get("birth_year") == 1990
    assert me_data.get("sex") == "female"
    assert me_data.get("addressing_preference") == "formal"

    user = db.query(models.User).filter(models.User.phone == phone).first()
    assert user is not None
    core = db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user.id).first()
    assert core is not None
    assert core.birth_year == 1990
    assert core.sex == "female"
    assert core.addressing_preference == "formal"


def test_patch_name_and_language_unified_fields(client: TestClient, db, monkeypatch):
    phone = "+989132222222"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"name": "Reza", "preferred_language": "fa"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data", {})
    assert data.get("name") == "Reza"
    assert data.get("display_name") == "Reza"
    assert data.get("preferred_language") == "fa"
    assert data.get("language") == "fa"


def test_patch_rejects_arbitrary_user_id(client: TestClient, db, monkeypatch):
    phone = "+989133333333"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"user_id": 99999, "name": "Hacker"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_patch_cannot_update_another_users_profile(client: TestClient, db, monkeypatch):
    phone_a = "+989134444441"
    phone_b = "+989134444442"
    token_a = _access_token_for_phone(client, db, monkeypatch, phone_a)
    token_b = _access_token_for_phone(client, db, monkeypatch, phone_b)

    r_a = client.patch(
        "/auth/me",
        json={"name": "User A", "birth_year": 1985, "sex": "male"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_a.status_code == 200, r_a.text

    me_b = client.get("/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_b.status_code == 200
    b_data = me_b.json().get("data", {})
    assert b_data.get("name") != "User A"
    assert b_data.get("birth_year") is None
    assert b_data.get("sex") is None


def test_user_context_includes_profile_core_fields(client: TestClient, db, monkeypatch):
    phone = "+989135555555"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    client.patch(
        "/auth/me",
        json={
            "name": "Neda",
            "birth_year": 1992,
            "sex": "female",
            "addressing_preference": "first_name",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    user = db.query(models.User).filter(models.User.phone == phone).first()
    from backend.app.services.user_context.user_context_service import UserContextService

    pack = UserContextService(db).get_user_context(user.id)
    assert pack.preferred_name == "Neda"
    assert pack.birth_year == 1992
    assert pack.sex == "female"
    assert pack.addressing_preference == "first_name"
