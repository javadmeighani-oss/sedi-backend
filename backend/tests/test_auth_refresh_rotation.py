# backend/tests/test_auth_refresh_rotation.py – Refresh token rotation (revoke used, issue new)
import os
import pytest
from unittest.mock import patch

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
    session = next(SessionLocal())
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_refresh_rotates_token_and_reusing_old_returns_401(db, monkeypatch):
    """Request OTP + verify_otp => refresh_token_1; /auth/refresh with it => 200 + refresh_token_2; reuse refresh_token_1 => 401."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_rotation")
    monkeypatch.setenv("REFRESH_SECRET", "test_refresh_rotation")
    code_plain = "123456"
    phone = "+989121111111"
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        ok, _ = svc.request_otp(db, phone)
    assert ok is True
    r1 = client.post("/auth/verify_otp", json={"phone": phone, "code": code_plain})
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1.get("ok") is True
    refresh_token_1 = data1["data"]["refresh_token"]
    assert refresh_token_1

    # First refresh: 200, get new tokens
    r2 = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token_1}"},
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2.get("ok") is True
    refresh_token_2 = data2["data"]["refresh_token"]
    assert refresh_token_2 != refresh_token_1
    assert "access_token" in data2["data"]

    # Reuse old refresh token => 401
    r3 = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token_1}"},
    )
    assert r3.status_code == 401
    assert "Invalid or expired refresh token" in (r3.json().get("detail") or "")

    # New token still works
    r4 = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token_2}"},
    )
    assert r4.status_code == 200
    assert r4.json().get("ok") is True


def test_refresh_rotation_only_one_unrevoked_per_user(db, monkeypatch):
    """After verify_otp + one refresh, DB has exactly one row with revoked_at NULL for that user."""
    monkeypatch.setenv("OTP_SECRET", "test_otp_rotation2")
    monkeypatch.setenv("REFRESH_SECRET", "test_refresh_rotation2")
    code_plain = "654321"
    phone = "+989122222222"
    with patch.object(svc, "generate_otp_code", return_value=code_plain):
        svc.request_otp(db, phone)
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": code_plain})
    assert r.status_code == 200
    refresh_1 = r.json()["data"]["refresh_token"]
    client.post("/auth/refresh", headers={"Authorization": f"Bearer {refresh_1}"})
    user = db.query(models.User).filter(models.User.phone == phone).first()
    assert user is not None
    unrevoked = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.user_id == user.id, models.RefreshToken.revoked_at.is_(None))
        .all()
    )
    assert len(unrevoked) == 1
    all_rows = db.query(models.RefreshToken).filter(models.RefreshToken.user_id == user.id).all()
    revoked_count = sum(1 for row in all_rows if row.revoked_at is not None)
    assert revoked_count >= 1
