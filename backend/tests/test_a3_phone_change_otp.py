"""Targeted phone-change OTP + LOGIN purpose isolation (Postgres/conftest)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

os.environ["SMS_DISABLED"] = "true"

from backend.app.core.security import create_access_token
from backend.app.models import OtpCode, User
from backend.app.services import auth_otp_service as svc


@pytest.fixture(autouse=True)
def _sms_disabled(monkeypatch):
    monkeypatch.setenv("SMS_DISABLED", "true")


def _token(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def test_login_otp_still_works(client, db):
    phone = "+15550001111"
    ok, err, code = svc.request_otp(db, phone)
    assert ok and not err and code
    user, verr = svc.verify_otp(db, phone, code)
    assert verr == ""
    assert user is not None
    assert user.phone == phone
    row = (
        db.query(OtpCode)
        .filter(OtpCode.phone == phone, OtpCode.purpose == svc.OTP_PURPOSE_LOGIN)
        .first()
    )
    assert row is not None


def test_phone_change_purpose_isolation_from_login(client, db):
    u = User(name="Iso", secret_key="t", preferred_language="en", phone="+15550002222")
    db.add(u)
    db.commit()
    db.refresh(u)

    ok, err, pc_code = svc.request_phone_change_otp(db, u, "+15550003333")
    assert ok and pc_code

    # LOGIN verify must NOT consume PHONE_CHANGE
    login_user, login_err = svc.verify_otp(db, "+15550003333", pc_code)
    assert login_err != ""
    assert login_user is None
    db.refresh(u)
    assert u.phone == "+15550002222"


def test_phone_change_requires_jwt(client, db):
    r = client.post("/auth/phone-change/request", json={"new_phone": "+15550004444"})
    assert r.status_code == 401


def test_same_phone_rejected(client, db):
    u = User(name="Same", secret_key="t", preferred_language="en", phone="+15550005555")
    db.add(u)
    db.commit()
    db.refresh(u)
    r = client.post(
        "/auth/phone-change/request",
        json={"new_phone": "+15550005555"},
        headers=_token(u.id),
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error", {}).get("code") == "PHONE_SAME"


def test_duplicate_phone_rejected(client, db):
    a = User(name="A", secret_key="t", preferred_language="en", phone="+15550006666")
    b = User(name="B", secret_key="t", preferred_language="en", phone="+15550007777")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    r = client.post(
        "/auth/phone-change/request",
        json={"new_phone": "+15550007777"},
        headers=_token(a.id),
    )
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error", {}).get("code") == "PHONE_DUPLICATE"


def test_wrong_otp_no_mutation(client, db):
    u = User(name="Wrong", secret_key="t", preferred_language="en", phone="+15550008888")
    db.add(u)
    db.commit()
    db.refresh(u)
    ok, _, code = svc.request_phone_change_otp(db, u, "+15550009999")
    assert ok and code
    r = client.post(
        "/auth/phone-change/verify",
        json={"new_phone": "+15550009999", "code": "000000"},
        headers=_token(u.id),
    )
    body = r.json()
    assert body.get("ok") is False
    db.refresh(u)
    assert u.phone == "+15550008888"


def test_expired_otp_no_mutation(client, db):
    u = User(name="Exp", secret_key="t", preferred_language="en", phone="+15550100001")
    db.add(u)
    db.commit()
    db.refresh(u)
    ok, _, code = svc.request_phone_change_otp(db, u, "+15550100002")
    assert ok and code
    row = (
        db.query(OtpCode)
        .filter(
            OtpCode.phone == "+15550100002",
            OtpCode.purpose == svc.OTP_PURPOSE_PHONE_CHANGE,
            OtpCode.user_id == u.id,
        )
        .first()
    )
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.add(row)
    db.commit()
    r = client.post(
        "/auth/phone-change/verify",
        json={"new_phone": "+15550100002", "code": code},
        headers=_token(u.id),
    )
    assert r.json().get("ok") is False
    db.refresh(u)
    assert u.phone == "+15550100001"


def test_successful_phone_change_same_account_id(client, db):
    u = User(name="Ok", secret_key="t", preferred_language="en", phone="+15550110001")
    db.add(u)
    db.commit()
    db.refresh(u)
    old_id = u.id
    ok, _, code = svc.request_phone_change_otp(db, u, "+15550110002")
    assert ok and code
    r = client.post(
        "/auth/phone-change/verify",
        json={"new_phone": "+15550110002", "code": code},
        headers=_token(u.id),
    )
    body = r.json()
    assert body.get("ok") is True, body
    data = body.get("data") or {}
    assert data.get("user_id") == old_id
    assert data.get("phone") == "+15550110002"
    db.refresh(u)
    assert u.id == old_id
    assert u.phone == "+15550110002"


def test_uniqueness_recheck_at_commit(client, db):
    a = User(name="RaceA", secret_key="t", preferred_language="en", phone="+15550120001")
    b = User(name="RaceB", secret_key="t", preferred_language="en", phone="+15550120002")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    ok, _, code = svc.request_phone_change_otp(db, a, "+15550120003")
    assert ok and code
    # Another account claims the target before verify
    b.phone = "+15550120003"
    db.add(b)
    db.commit()
    r = client.post(
        "/auth/phone-change/verify",
        json={"new_phone": "+15550120003", "code": code},
        headers=_token(a.id),
    )
    assert r.json().get("ok") is False
    db.refresh(a)
    assert a.phone == "+15550120001"


def test_login_with_new_phone_same_account_old_gone(client, db):
    u = User(name="Cont", secret_key="t", preferred_language="en", phone="+15550130001")
    db.add(u)
    db.commit()
    db.refresh(u)
    account_id = u.id
    ok, _, code = svc.request_phone_change_otp(db, u, "+15550130002")
    assert ok and code
    updated, err = svc.verify_phone_change_otp(db, u, "+15550130002", code)
    assert err == "" and updated is not None
    assert updated.id == account_id

    # New phone LOGIN finds same account
    ok2, _, login_code = svc.request_otp(db, "+15550130002")
    assert ok2 and login_code
    found, verr = svc.verify_otp(db, "+15550130002", login_code)
    assert verr == "" and found is not None
    assert found.id == account_id

    # Old phone no longer identifies this account
    orphan = db.query(User).filter(User.phone == "+15550130001").first()
    assert orphan is None or orphan.id != account_id


def test_auth_me_returns_new_phone(client, db):
    u = User(name="Me", secret_key="t", preferred_language="en", phone="+15550140001")
    db.add(u)
    db.commit()
    db.refresh(u)
    ok, _, code = svc.request_phone_change_otp(db, u, "+15550140002")
    assert ok and code
    client.post(
        "/auth/phone-change/verify",
        json={"new_phone": "+15550140002", "code": code},
        headers=_token(u.id),
    )
    me = client.get("/auth/me", headers=_token(u.id))
    assert me.status_code == 200
    data = (me.json().get("data") or {})
    assert data.get("phone") == "+15550140002"
    assert data.get("user_id") == u.id


def test_cross_account_cannot_verify_other_users_otp(client, db):
    a = User(name="XA", secret_key="t", preferred_language="en", phone="+15550150001")
    b = User(name="XB", secret_key="t", preferred_language="en", phone="+15550150002")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    ok, _, code = svc.request_phone_change_otp(db, a, "+15550150003")
    assert ok and code
    # B tries to verify A's challenge
    r = client.post(
        "/auth/phone-change/verify",
        json={"new_phone": "+15550150003", "code": code},
        headers=_token(b.id),
    )
    assert r.json().get("ok") is False
    db.refresh(a)
    db.refresh(b)
    assert a.phone == "+15550150001"
    assert b.phone == "+15550150002"
