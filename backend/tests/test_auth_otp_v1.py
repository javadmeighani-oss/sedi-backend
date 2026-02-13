# backend/tests/test_auth_otp_v1.py – Stage 25 Phone OTP auth tests
import os
import pytest
from datetime import datetime, timedelta

# Force dev mode so request_otp does not require SMS (log only)
os.environ["SMS_DISABLED"] = "true"

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, Base, engine
from backend.app.main import app
from backend.app import models
from backend.app.services import auth_otp_service as svc

client = TestClient(app)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_request_otp_returns_ok_with_sms_disabled(db):
    """request_otp returns ok and next=verify_otp when SMS_DISABLED=true."""
    r = client.post("/auth/request_otp", json={"phone": "+989121234567"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("data", {}).get("next") == "verify_otp"


def test_verify_otp_with_correct_code_issues_tokens_and_creates_user(db):
    """Request OTP, then verify with correct code; get tokens and user created."""
    phone = "+989123456789"
    # Request OTP (dev mode logs code; we need to get code from OtpCode row for test)
    ok, _ = svc.request_otp(db, phone)
    assert ok is True
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == phone).first()
    assert row is not None
    # We cannot get plain code from DB (hashed). So use service to verify by generating same code - we can't.
    # Instead: in test we need to either (1) mock hash/verify to accept a known code, or (2) read code from log.
    # Simplest: patch or inject a fixed OTP in test. E.g. in request_otp we store hashed; in test we could
    # create OtpCode manually with a known code hash (hash "123456") and then verify_otp(phone, "123456").
    code_plain = "123456"
    from passlib.context import CryptContext
    row.code_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(code_plain)
    row.attempts = 0
    row.expires_at = datetime.utcnow() + timedelta(minutes=5)
    db.commit()
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


def test_verify_otp_wrong_code_increments_attempts_and_fails(db):
    """verify_otp with wrong code returns error and increments attempts."""
    phone = "+989199999999"
    ok, _ = svc.request_otp(db, phone)
    assert ok is True
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": "000000"})
    assert r.status_code == 200  # API returns 200 with ok=False
    data = r.json()
    assert data.get("ok") is False
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == phone).first()
    assert row.attempts == 1


def test_auth_me_works_with_access_token(db):
    """GET /auth/me with valid Bearer returns user info."""
    phone = "+989128888888"
    ok, _ = svc.request_otp(db, phone)
    assert ok is True
    # Set a known code for this phone
    from passlib.context import CryptContext
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == phone).first()
    row.code_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash("654321")
    row.attempts = 0
    db.commit()
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": "654321"})
    assert r.status_code == 200 and r.json().get("ok") is True
    access_token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    me_data = me.json().get("data", {})
    assert me_data.get("phone") == phone
    assert "user_id" in me_data
