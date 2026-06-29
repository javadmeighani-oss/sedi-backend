"""Gate 1 — caregiver contact registry."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_caregivers_crud_and_priority(client, db, monkeypatch):
    phone = "+989143003001"
    token = _token(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}

    c1 = client.post(
        "/user/caregivers",
        json={"name": "Ali", "phone": "+989120000001", "relationship": "brother", "priority": 2},
        headers=headers,
    )
    assert c1.status_code == 200
    c2 = client.post(
        "/user/caregivers",
        json={"name": "Sara", "relationship": "daughter", "priority": 1},
        headers=headers,
    )
    assert c2.status_code == 200
    cid = c2.json()["data"]["id"]

    listed = client.get("/user/caregivers", headers=headers).json()["data"]["caregivers"]
    assert listed[0]["name"] == "Sara"

    patched = client.patch(
        f"/user/caregivers/{cid}",
        json={"notify_emergency": False, "can_manage_profile": True},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["can_manage_profile"] is True

    deleted = client.delete(f"/user/caregivers/{cid}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["soft"] is True


def test_caregivers_cross_user_denied(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989143003002")
    t2 = _token(client, db, monkeypatch, "+989143003003")
    cid = client.post(
        "/user/caregivers",
        json={"name": "Mom"},
        headers={"Authorization": f"Bearer {t1}"},
    ).json()["data"]["id"]
    assert client.patch(
        f"/user/caregivers/{cid}",
        json={"name": "Hacked"},
        headers={"Authorization": f"Bearer {t2}"},
    ).status_code == 404
