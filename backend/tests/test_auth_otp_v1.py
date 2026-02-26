# backend/tests/test_auth_otp_v1.py – Stage 25 Phone OTP auth tests
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

# Force dev mode so request_otp does not require SMS (log only)
os.environ["SMS_DISABLED"] = "true"

from fastapi.testclient import TestClient

from backend.app import models
from backend.app.services import auth_otp_service as svc


def test_request_otp_returns_ok_with_sms_disabled(client: TestClient, db):
    """request_otp returns ok and next=verify_otp when SMS_DISABLED=true."""
    r = client.post("/auth/request_otp", json={"phone": "+989121234567"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("data", {}).get("next") == "verify_otp"


def test_verify_otp_with_correct_code_issues_tokens_and_creates_user(client: TestClient, db, monkeypatch):
    """Request OTP with mocked code; verify with same code; tokens and user created (HMAC OTP)."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_123")
    code_plain = "123456"
    phone = "+989123456789"
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _ = svc.request_otp(db, phone)
    assert ok is True
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == phone).first()
    assert row is not None
    assert row.code_hash  # HMAC hex digest stored
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": code_plain})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    payload = data.get("data", {})
    assert "access_token" in payload
    assert "refresh_token" in payload
    assert payload.get("token_type") == "bearer"
    user = db.query(models.User).filter(models.User.phone == phone).first()
    assert user is not None


def test_verify_otp_stores_device_info_and_ip_when_headers_present(client: TestClient, db, monkeypatch):
    """verify_otp with X-Device-Info and X-Client-IP stores them on the refresh token row (A3.2)."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_device")
    code_plain = "111222"
    phone = "+989177777777"
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _ = svc.request_otp(db, phone)
    assert ok is True
    r = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": code_plain},
        headers={"X-Device-Info": "TestDevice/1.0", "X-Client-IP": "192.168.1.100"},
    )
    assert r.status_code == 200 and r.json().get("ok") is True
    user = db.query(models.User).filter(models.User.phone == phone).first()
    assert user is not None
    rt = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.user_id == user.id)
        .order_by(models.RefreshToken.created_at.desc())
        .first()
    )
    assert rt is not None
    assert rt.device_info == "TestDevice/1.0"
    assert rt.ip == "192.168.1.100"


def test_verify_otp_wrong_code_increments_attempts_and_fails(client: TestClient, db, monkeypatch):
    """verify_otp with wrong code returns error and increments attempts (HMAC OTP)."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_456")
    phone = "+989199999999"
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        ok, _ = svc.request_otp(db, phone)
    assert ok is True
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": "000000"})
    assert r.status_code == 200  # API returns 200 with ok=False
    data = r.json()
    assert data.get("ok") is False
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == phone).first()
    assert row.attempts == 1


def test_auth_me_works_with_access_token(client: TestClient, db, monkeypatch):
    """GET /auth/me with valid Bearer returns user info (HMAC OTP)."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_me")
    phone = "+989128888888"
    with patch.object(svc, "generate_otp_code", return_value="654321"):
        ok, _ = svc.request_otp(db, phone)
    assert ok is True
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": "654321"})
    assert r.status_code == 200 and r.json().get("ok") is True
    access_token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    me_data = me.json().get("data", {})
    assert me_data.get("phone") == phone
    assert "user_id" in me_data


def test_sms_disabled_does_not_call_provider(client: TestClient, db):
    """When SMS_DISABLED=true, request_otp does not call get_sms_sender (Stage 25 Step 2.2)."""
    with patch("backend.app.services.sms_gateway.get_sms_sender") as mock_get:
        ok, err = svc.request_otp(db, "+989100000001")
        mock_get.assert_not_called()
        assert ok is True
        assert err == ""


def test_request_otp_succeeds_with_dummy_provider(client: TestClient, db):
    """When SMS_DISABLED=false and SMS_PROVIDER=dummy, request_otp succeeds without network (Stage 25 Step 2.2)."""
    with patch.object(svc, "SMS_DISABLED", False):
        with patch.dict(os.environ, {"SMS_PROVIDER": "dummy"}, clear=False):
            ok, err = svc.request_otp(db, "+989100000002")
            assert ok is True
            assert err == ""


def test_resolve_lang():
    """resolve_lang parses Accept-Language; V1 default is en (English primary)."""
    assert svc.resolve_lang(None) == "en"
    assert svc.resolve_lang("") == "en"
    assert svc.resolve_lang("en-US,en;q=0.9") == "en"
    assert svc.resolve_lang("fa") == "fa"
    assert svc.resolve_lang("ar-EG") == "ar"
    assert svc.resolve_lang("fr-FR") == "en"  # unknown -> en (V1 policy)


def test_otp_hmac_deterministic_and_compare_digest(monkeypatch):
    """_otp_hmac is deterministic; same code+secret gives same hash; wrong code fails compare."""
    import hmac
    monkeypatch.setenv("OTP_SECRET", "fixed_secret")
    # Reload or call through module so it picks up env
    h1 = svc._otp_hmac("123456")
    h2 = svc._otp_hmac("123456")
    assert h1 == h2
    assert len(h1) == 64  # SHA256 hex
    assert h1.isalnum()
    other = svc._otp_hmac("000000")
    assert other != h1
    assert hmac.compare_digest(h1, h2) is True
    assert hmac.compare_digest(h1, other) is False
