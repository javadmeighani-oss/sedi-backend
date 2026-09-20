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
    """request_otp returns ok, next=verify_otp, and dev_code when SMS_DISABLED=true."""
    r = client.post("/auth/request_otp", json={"phone": "+989121234567"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    resp_data = data.get("data", {})
    assert resp_data.get("next") == "verify_otp"
    dev_code = resp_data.get("dev_code")
    assert dev_code is not None and len(dev_code) == 6 and dev_code.isdigit()


def test_otp_request_alias_works_same_as_request_otp(client: TestClient, db):
    """POST /auth/otp/request is alias for /auth/request_otp; both must work (not 404)."""
    r = client.post("/auth/otp/request", json={"phone": "+989121234568"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("ok") is True
    assert (data.get("data") or {}).get("next") == "verify_otp"


def test_login_existing_issues_tokens(client: TestClient, db, monkeypatch):
    """LOGIN OTP verifies an existing account and issues tokens."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_123")
    code_plain = "123456"
    phone = "+989123456789"
    user = models.User(phone=phone, name="Login", secret_key="test", preferred_language="en")
    db.add(user)
    db.commit()
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _, _ = svc.request_otp(db, phone)
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
    assert payload.get("user_id") == user.id


def test_login_unknown_returns_account_not_found_and_does_not_create_user(
    client: TestClient, db, monkeypatch
):
    """LOGIN can verify an OTP, but unknown phones must not create accounts."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_login_unknown")
    code_plain = "444555"
    phone = "+989123450001"
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _, _ = svc.request_otp(db, phone)
    assert ok is True
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": code_plain})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error", {}).get("code") == "ACCOUNT_NOT_FOUND"
    assert db.query(models.User).filter(models.User.phone == phone).first() is None


def test_registration_unknown_creates_user_only_after_valid_otp(client: TestClient, db, monkeypatch):
    """REGISTRATION creates an account only after a valid purpose-bound OTP."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_registration")
    code_plain = "222333"
    phone = "+989123450002"
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION)
    assert ok is True

    wrong = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": "000000", "purpose": "REGISTRATION"},
    )
    assert wrong.status_code == 200
    assert wrong.json().get("ok") is False
    assert db.query(models.User).filter(models.User.phone == phone).first() is None

    r = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": code_plain, "purpose": "REGISTRATION"},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    user = db.query(models.User).filter(models.User.phone == phone).first()
    assert user is not None


def test_registration_existing_returns_account_exists_no_duplicate(client: TestClient, db, monkeypatch):
    """REGISTRATION with a valid OTP must reject existing phones and avoid duplicates."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_registration_existing")
    code_plain = "333444"
    phone = "+989123450003"
    user = models.User(phone=phone, name="Existing", secret_key="test", preferred_language="en")
    db.add(user)
    db.commit()
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION)
    assert ok is True
    r = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": code_plain, "purpose": "REGISTRATION"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error", {}).get("code") == "ACCOUNT_EXISTS"
    assert db.query(models.User).filter(models.User.phone == phone).count() == 1


def test_login_registration_purpose_isolation(client: TestClient, db, monkeypatch):
    """A REGISTRATION code cannot satisfy LOGIN verification for the same phone."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_purpose_iso")
    phone = "+989123450004"
    db.add(models.User(phone=phone, name="PurposeIso", secret_key="test", preferred_language="en"))
    db.commit()
    with patch.object(svc, "generate_otp_code", return_value="555666"):
        ok, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION)
    assert ok is True

    r = client.post("/auth/verify_otp", json={"phone": phone, "code": "555666"})
    assert r.status_code == 200
    assert r.json().get("ok") is False
    assert "access_token" not in (r.json().get("data") or {})


def test_request_otp_rate_limit_is_isolated_by_purpose(db, monkeypatch):
    """LOGIN and REGISTRATION maintain separate rate-limit buckets."""
    monkeypatch.setattr(svc, "OTP_RATE_LIMIT_COUNT", 1)
    phone = "+989123450005"
    with patch.object(svc, "generate_otp_code", return_value="101010"):
        ok_login, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
        ok_registration, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION)
        ok_login_again, err, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
    assert ok_login is True
    assert ok_registration is True
    assert ok_login_again is False
    assert "Too many OTP requests" in err


def test_request_otp_rate_window_resets_sent_count_outside_window(db, monkeypatch):
    """Outside-window OTP row must start a new window with sent_count=1 (relogin counter bug)."""
    monkeypatch.setattr(svc, "OTP_RATE_LIMIT_COUNT", 3)
    monkeypatch.setattr(svc, "OTP_RATE_LIMIT_WINDOW_MINUTES", 10)
    phone = "+989123450091"
    with patch.object(svc, "generate_otp_code", return_value="555555"):
        ok, err, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
    assert ok is True
    assert err == ""
    row = (
        db.query(models.OtpCode)
        .filter(
            models.OtpCode.phone == phone,
            models.OtpCode.purpose == svc.OTP_PURPOSE_LOGIN,
        )
        .first()
    )
    assert row is not None
    # Simulate exhausted prior window carried on the reused row.
    row.sent_count = 5
    row.created_at = datetime.utcnow() - timedelta(minutes=11)
    db.commit()

    with patch.object(svc, "generate_otp_code", return_value="555556"):
        ok2, err2, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
    assert ok2 is True, err2
    db.refresh(row)
    assert row.sent_count == 1

    with patch.object(svc, "generate_otp_code", return_value="555557"):
        ok3, err3, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
    assert ok3 is True, err3
    db.refresh(row)
    assert row.sent_count == 2

    with patch.object(svc, "generate_otp_code", return_value="555558"):
        ok4, err4, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
    assert ok4 is True, err4
    db.refresh(row)
    assert row.sent_count == 3

    with patch.object(svc, "generate_otp_code", return_value="555559"):
        ok5, err5, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
    assert ok5 is False
    assert "Too many OTP requests" in err5
    db.refresh(row)
    assert row.sent_count == 3


def test_request_otp_rate_window_reset_keeps_login_registration_isolation(db, monkeypatch):
    """Window reset must not mix LOGIN and REGISTRATION buckets."""
    monkeypatch.setattr(svc, "OTP_RATE_LIMIT_COUNT", 1)
    monkeypatch.setattr(svc, "OTP_RATE_LIMIT_WINDOW_MINUTES", 10)
    phone = "+989123450092"
    with patch.object(svc, "generate_otp_code", return_value="606060"):
        assert svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)[0] is True
        assert svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION)[0] is True

    login_row = (
        db.query(models.OtpCode)
        .filter(
            models.OtpCode.phone == phone,
            models.OtpCode.purpose == svc.OTP_PURPOSE_LOGIN,
        )
        .first()
    )
    reg_row = (
        db.query(models.OtpCode)
        .filter(
            models.OtpCode.phone == phone,
            models.OtpCode.purpose == svc.OTP_PURPOSE_REGISTRATION,
        )
        .first()
    )
    assert login_row is not None and reg_row is not None
    login_row.sent_count = 9
    login_row.created_at = datetime.utcnow() - timedelta(minutes=15)
    reg_row.sent_count = 9
    reg_row.created_at = datetime.utcnow() - timedelta(minutes=15)
    db.commit()

    with patch.object(svc, "generate_otp_code", return_value="606061"):
        ok_l, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
        ok_r, _, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION)
    assert ok_l is True
    assert ok_r is True
    db.refresh(login_row)
    db.refresh(reg_row)
    assert login_row.sent_count == 1
    assert reg_row.sent_count == 1


def test_phone_change_otp_rate_window_reset_preserves_user_binding(db, monkeypatch):
    """PHONE_CHANGE outside-window reuse resets sent_count and stays user-bound."""
    monkeypatch.setattr(svc, "OTP_RATE_LIMIT_COUNT", 2)
    monkeypatch.setattr(svc, "OTP_RATE_LIMIT_WINDOW_MINUTES", 10)
    user = models.User(
        phone="+989123450093",
        name="PC",
        secret_key="test",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    new_phone = "+989123450094"

    with patch.object(svc, "generate_otp_code", return_value="707070"):
        ok, err, _ = svc.request_phone_change_otp(db, user, new_phone)
    assert ok is True, err
    row = (
        db.query(models.OtpCode)
        .filter(
            models.OtpCode.phone == new_phone,
            models.OtpCode.purpose == svc.OTP_PURPOSE_PHONE_CHANGE,
            models.OtpCode.user_id == user.id,
        )
        .first()
    )
    assert row is not None
    row.sent_count = 8
    row.created_at = datetime.utcnow() - timedelta(minutes=20)
    db.commit()

    with patch.object(svc, "generate_otp_code", return_value="707071"):
        ok2, err2, _ = svc.request_phone_change_otp(db, user, new_phone)
    assert ok2 is True, err2
    db.refresh(row)
    assert row.sent_count == 1
    assert row.user_id == user.id
    assert row.purpose == svc.OTP_PURPOSE_PHONE_CHANGE


def test_verify_otp_expired_and_attempt_limits_for_login(client: TestClient, db, monkeypatch):
    """LOGIN preserves expiry and attempt-limit behavior for existing accounts."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_login_limits")
    expired_phone = "+989123450006"
    db.add(models.User(phone=expired_phone, name="Expired", secret_key="test", preferred_language="en"))
    db.commit()
    with patch.object(svc, "generate_otp_code", return_value="121212"):
        ok, _, _ = svc.request_otp(db, expired_phone)
    assert ok is True
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == expired_phone).first()
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    expired = client.post("/auth/verify_otp", json={"phone": expired_phone, "code": "121212"})
    assert expired.json().get("error", {}).get("code") == "OTP_EXPIRED"

    attempts_phone = "+989123450007"
    db.add(models.User(phone=attempts_phone, name="Attempts", secret_key="test", preferred_language="en"))
    db.commit()
    with patch.object(svc, "generate_otp_code", return_value="343434"):
        ok, _, _ = svc.request_otp(db, attempts_phone)
    assert ok is True
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == attempts_phone).first()
    row.attempts = svc.OTP_MAX_ATTEMPTS
    db.commit()
    limited = client.post("/auth/verify_otp", json={"phone": attempts_phone, "code": "343434"})
    assert limited.json().get("error", {}).get("code") == "TOO_MANY_ATTEMPTS"


def test_verify_otp_stores_device_info_and_ip_when_headers_present(client: TestClient, db, monkeypatch):
    """verify_otp with X-Device-Info and X-Client-IP stores them on the refresh token row (A3.2)."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_secret_device")
    code_plain = "111222"
    phone = "+989177777777"
    db.add(models.User(phone=phone, name="Device", secret_key="test", preferred_language="en"))
    db.commit()
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _, _ = svc.request_otp(db, phone)
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
        ok, _, _ = svc.request_otp(db, phone)
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
    db.add(models.User(phone=phone, name="Me", secret_key="test", preferred_language="en"))
    db.commit()
    with patch.object(svc, "generate_otp_code", return_value="654321"):
        ok, _, _ = svc.request_otp(db, phone)
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
        ok, err, _ = svc.request_otp(db, "+989100000001")
        mock_get.assert_not_called()
        assert ok is True
        assert err == ""


def test_request_otp_succeeds_with_dummy_provider(client: TestClient, db):
    """When SMS_DISABLED=false and SMS_PROVIDER=dummy, request_otp succeeds without network (Stage 25 Step 2.2)."""
    with patch.dict(os.environ, {"SMS_DISABLED": "false", "SMS_PROVIDER": "dummy"}, clear=False):
        ok, err, dev_code = svc.request_otp(db, "+989100000002")
        assert ok is True
        assert err == ""
        assert dev_code is None  # dummy succeeds, no dev_code


def test_request_otp_returns_error_when_sms_send_fails(client: TestClient, db):
    """When SMS is enabled but provider fails, request_otp returns (False, error_msg, None) - no dev_code."""
    with patch.dict(
        os.environ,
        {
            "SMS_DISABLED": "false",
            "SMS_PROVIDER": "mediana",
            "MEDIANA_API_KEY": "",
            "MEDIANA_OTP_PATTERN_CODE": "test-pattern",
        },
        clear=False,
    ):
        ok, err, dev_code = svc.request_otp(db, "+989100000003")
        assert ok is False
        assert "MEDIANA" in err or "not set" in err.lower() or "SMS" in err
        assert dev_code is None


def test_otp_request_returns_success_when_mediana_accepts_with_message(client: TestClient, db):
    """Regression: Mediana may return bulk_id plus message text on successful OTP send."""
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"bulk_id":"track-otp-1","message":"OTP sent successfully"}'
    mock_response.json.return_value = {
        "bulk_id": "track-otp-1",
        "message": "OTP sent successfully",
    }

    with patch.dict(
        os.environ,
        {
            "SMS_DISABLED": "false",
            "SMS_PROVIDER": "mediana",
            "MEDIANA_API_KEY": "test-key",
            "MEDIANA_OTP_PATTERN_CODE": "test-pattern",
        },
        clear=False,
    ), patch("requests.post", return_value=mock_response):
        ok, err, dev_code = svc.request_otp(db, "+989121234567")

    assert ok is True
    assert err == ""
    assert dev_code is None


def test_request_otp_succeeds_when_mediana_returns_in_progress_message(client: TestClient, db):
    """Regression: Mediana may respond with 'در حال ساخت' while SMS is delivered."""
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"message":"\\u062f\\u0631 \\u062d\\u0627\\u0644 \\u0633\\u0627\\u062e\\u062a"}'
    mock_response.json.return_value = {"message": "در حال ساخت"}

    with patch.dict(
        os.environ,
        {
            "SMS_DISABLED": "false",
            "SMS_PROVIDER": "mediana",
            "MEDIANA_API_KEY": "test-key",
            "MEDIANA_OTP_PATTERN_CODE": "test-pattern",
        },
        clear=False,
    ), patch("requests.post", return_value=mock_response):
        ok, err, dev_code = svc.request_otp(db, "+989121234567")

    assert ok is True
    assert err == ""
    assert dev_code is None


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
