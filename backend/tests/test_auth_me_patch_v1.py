import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

import pytest
from fastapi.testclient import TestClient

from backend.app.services import auth_otp_service as svc


def _access_token_for_phone(client: TestClient, db, monkeypatch, phone: str, code: str = "123456") -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_secret_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value=code):
        ok, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION)
    assert ok is True
    verify = client.post("/auth/verify_otp", json={"phone": phone, "code": code, "purpose": "REGISTRATION"})
    assert verify.status_code == 200 and verify.json().get("ok") is True
    return verify.json()["data"]["access_token"]


def test_patch_auth_me_requires_auth(client: TestClient):
    r = client.patch("/auth/me", json={"preferred_language": "fa"})
    assert r.status_code == 401


def test_patch_auth_me_updates_preferred_language_fa(client: TestClient, db, monkeypatch):
    phone = "+989121111111"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"preferred_language": "fa"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data", {})
    assert data.get("language") == "fa"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json().get("data", {}).get("language") == "fa"


def test_patch_auth_me_updates_preferred_language_ar(client: TestClient, db, monkeypatch):
    phone = "+989122222222"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"preferred_language": "ar"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("data", {}).get("language") == "ar"


def test_patch_auth_me_rejects_unsupported_language(client: TestClient, db, monkeypatch):
    phone = "+989123333333"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"preferred_language": "fr"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_patch_auth_me_updates_display_name(client: TestClient, db, monkeypatch):
    phone = "+989124444444"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"display_name": "  Ali Reza  "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("data", {}).get("display_name") == "Ali Reza"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json().get("data", {}).get("display_name") == "Ali Reza"


def test_patch_auth_me_rejects_empty_display_name(client: TestClient, db, monkeypatch):
    phone = "+989125555555"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    r = client.patch(
        "/auth/me",
        json={"display_name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_patch_auth_me_get_reflects_both_updates(client: TestClient, db, monkeypatch):
    phone = "+989126666666"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    patch_res = client.patch(
        "/auth/me",
        json={"preferred_language": "en", "display_name": "Sara"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 200, patch_res.text

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    me_data = me.json().get("data", {})
    assert me_data.get("language") == "en"
    assert me_data.get("display_name") == "Sara"
    assert me_data.get("phone") == phone
    assert "user_id" in me_data


def test_patch_auth_me_language_mirrors_knowledge_and_core_copies(client: TestClient, db, monkeypatch):
    """The account language is also stored in UserProfileKnowledge and UserProfileCore; they must follow it."""
    from backend.app import models
    from backend.app.services.user_context.user_context_service import UserContextService

    phone = "+989125555555"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    user = db.query(models.User).filter(models.User.phone == phone).first()
    assert user is not None
    db.add(models.UserProfileKnowledge(user_id=user.id, display_name="Sara", language="fa"))
    db.add(models.UserProfileCore(user_id=user.id, language="fa"))
    db.commit()

    r = client.patch(
        "/auth/me",
        json={"preferred_language": "en"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    knowledge = db.query(models.UserProfileKnowledge).filter_by(user_id=user.id).first()
    core = db.query(models.UserProfileCore).filter_by(user_id=user.id).first()
    assert knowledge.language == "en"
    assert core.language == "en"
    assert UserContextService(db).get_user_context(user.id).language == "en"


def test_patch_auth_me_language_without_copies_creates_nothing(client: TestClient, db, monkeypatch):
    from backend.app import models

    phone = "+989126666666"
    token = _access_token_for_phone(client, db, monkeypatch, phone)
    user = db.query(models.User).filter(models.User.phone == phone).first()
    before = db.query(models.UserProfileKnowledge).filter_by(user_id=user.id).count()

    r = client.patch(
        "/auth/me",
        json={"preferred_language": "ar"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert db.query(models.UserProfileKnowledge).filter_by(user_id=user.id).count() == before
