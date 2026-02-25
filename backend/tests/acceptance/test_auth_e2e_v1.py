"""
Acceptance A3: Auth E2E V1 flow

Scenario:
request_otp -> verify_otp -> /auth/me -> refresh -> logout -> verify token invalidation behavior
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services import auth_otp_service as otp_svc
from backend.tests.test_db_config import get_test_database_url


_BLOCKED_DB_SUBSTRINGS = ("sedi_db", "prod", "production")


def _is_production_db_url(url: str) -> bool:
    u = (url or "").lower()
    return any(blocked in u for blocked in _BLOCKED_DB_SUBSTRINGS)


def _env_indicates_production() -> bool:
    env = (os.environ.get("ENV") or "").lower()
    app_env = (os.environ.get("APP_ENV") or "").lower()
    return env == "production" or app_env == "production"


_test_db_url = get_test_database_url()
if _env_indicates_production():
    raise RuntimeError("Refusing to run acceptance tests: ENV or APP_ENV indicates production.")
if _is_production_db_url(_test_db_url):
    raise RuntimeError(
        "Refusing to run acceptance tests against a production-like DB URL. "
        "Set TEST_DATABASE_URL to a safe test database (e.g. sedi_test)."
    )


@pytest.fixture
def auth_e2e_user(db: Session) -> models.User:
    user = db.query(models.User).filter(models.User.id == 1001).first()
    if user is None:
        user = models.User(
            id=1001,
            name="Auth E2E User",
            phone="+989100000001",
            secret_key="auth-e2e-secret",
            preferred_language="en",
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.preferred_language = "en"
        db.commit()
        db.refresh(user)
    return user


def _read_first_present_string(payload: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _otp_from_request_response(response_json: dict) -> str | None:
    data = response_json.get("data")
    if not isinstance(data, dict):
        return None
    return _read_first_present_string(data, ("otp", "code", "debug_code", "otp_code"))


def _otp_from_db_if_plaintext_exists(db: Session, phone: str) -> str | None:
    # First try ORM attributes (if schema has plaintext/debug columns).
    row = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.phone == phone)
        .order_by(models.OtpCode.created_at.desc())
        .first()
    )
    if row is not None:
        for attr in ("otp", "code", "debug_code", "otp_code"):
            value = getattr(row, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()

    # Then try raw SQL mapping in case DB has extra columns not on ORM model.
    raw = db.execute(
        text("SELECT * FROM otp_codes WHERE phone = :phone ORDER BY created_at DESC LIMIT 1"),
        {"phone": phone},
    ).mappings().first()
    if raw is not None:
        for key in ("otp", "code", "debug_code", "otp_code"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _obtain_otp_code(
    response_json: dict,
    db: Session,
    phone: str,
    *,
    controlled_fallback: str | None = None,
) -> str:
    # 1) Preferred: debug OTP from request_otp response
    from_response = _otp_from_request_response(response_json)
    if from_response:
        return from_response

    # 2) Fallback: latest OTP plaintext/debug field from DB (if available)
    from_db = _otp_from_db_if_plaintext_exists(db, phone)
    if from_db:
        return from_db

    # Test-controlled fallback for hash-only OTP storage:
    # request_otp was called with patched generator, so this is deterministic (not a blind guess).
    if controlled_fallback:
        return controlled_fallback

    pytest.fail("Cannot obtain OTP in test env")


def test_auth_e2e_v1_request_verify_me_refresh_logout(
    client: TestClient,
    db: Session,
    auth_e2e_user: models.User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMS_DISABLED", "true")
    monkeypatch.setenv("OTP_SECRET", "acceptance-auth-e2e-otp-secret")
    monkeypatch.setenv("REFRESH_SECRET", "acceptance-auth-e2e-refresh-secret")

    phone = auth_e2e_user.phone or "+989100000001"
    forced_otp_code = "123456"

    with patch.object(otp_svc, "generate_otp_code", return_value=forced_otp_code):
        request_otp_res = client.post(
            "/auth/request_otp",
            json={"phone": phone},
            headers={"Accept-Language": "en"},
        )
    assert request_otp_res.status_code == 200, request_otp_res.text
    request_otp_json = request_otp_res.json()
    assert request_otp_json.get("ok") is True
    assert (request_otp_json.get("data") or {}).get("next") == "verify_otp"

    otp_code = _obtain_otp_code(
        request_otp_json,
        db,
        phone,
        controlled_fallback=forced_otp_code,
    )

    verify_res = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": otp_code},
        headers={"X-Device-Info": "A3AuthE2E/1.0", "X-Client-IP": "127.0.0.10"},
    )
    assert verify_res.status_code == 200, verify_res.text
    verify_json = verify_res.json()
    assert verify_json.get("ok") is True, verify_json

    tokens = verify_json.get("data") or {}
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    assert isinstance(access_token, str) and access_token
    assert isinstance(refresh_token, str) and refresh_token

    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_res.status_code == 200, me_res.text
    me_json = me_res.json()
    assert me_json.get("ok") is True
    assert (me_json.get("data") or {}).get("phone") == phone

    refresh_res = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert refresh_res.status_code == 200, refresh_res.text
    refresh_json = refresh_res.json()
    assert refresh_json.get("ok") is True

    refreshed = refresh_json.get("data") or {}
    access_token_2 = refreshed.get("access_token")
    refresh_token_2 = refreshed.get("refresh_token")
    assert isinstance(access_token_2, str) and access_token_2
    assert isinstance(refresh_token_2, str) and refresh_token_2
    assert refresh_token_2 != refresh_token

    logout_res = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {refresh_token_2}"},
    )
    assert logout_res.status_code == 200, logout_res.text
    logout_json = logout_res.json()
    assert logout_json.get("ok") is True
    assert (logout_json.get("data") or {}).get("revoked") is True

    # Token invalidation verification: refresh token used in logout must be unusable.
    refresh_after_logout = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token_2}"},
    )
    assert refresh_after_logout.status_code == 401

    # Access token behavior after logout depends on implementation.
    # Current implementation validates stateless JWT access tokens and revokes refresh tokens only.
    me_after_logout = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token_2}"})
    assert me_after_logout.status_code in (200, 401, 403), me_after_logout.text
    if me_after_logout.status_code == 200:
        assert me_after_logout.json().get("ok") is True
