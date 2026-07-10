"""Section 10 — caregiver notify_vital_alerts, phone normalization, duplicates."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc

CAREGIVER_RESPONSE_FIELDS = frozenset({
    "id",
    "name",
    "phone",
    "relationship",
    "is_active",
    "notify_daily_status",
    "notify_care_summary",
    "notify_vital_alerts",
    "notify_emergency",
    "emergency_priority",
})


def _assert_caregiver_contract(body: dict) -> None:
    assert body.get("ok") is True
    data = body["data"]
    assert CAREGIVER_RESPONSE_FIELDS.issubset(data.keys())
    assert data["notify_vital_alerts"] is False or isinstance(data["notify_vital_alerts"], bool)
    assert data["emergency_priority"] is None or isinstance(data["emergency_priority"], int)
    assert "diagnosis" not in data
    assert "arrhythmia" not in str(data).lower()


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_caregiver_notify_vital_alerts_crud(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003010")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/user/caregivers",
        json={
            "name": "Nurse",
            "phone": "09120000010",
            "notify_vital_alerts": True,
            "notify_care_summary": False,
            "emergency_priority": 1,
        },
        headers=headers,
    )
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["notify_vital_alerts"] is True
    assert data["notify_care_summary"] is False
    assert data["phone"] == "+989120000010"
    assert data["emergency_priority"] == 1

    cid = data["id"]
    patched = client.patch(
        f"/user/caregivers/{cid}",
        json={"notify_vital_alerts": False},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["notify_vital_alerts"] is False


def test_caregiver_duplicate_active_phone_conflict(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003011")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post(
        "/user/caregivers",
        json={"name": "A", "phone": "+989120000011"},
        headers=headers,
    ).status_code == 200

    dup = client.post(
        "/user/caregivers",
        json={"name": "B", "phone": "989120000011"},
        headers=headers,
    )
    assert dup.status_code == 409


def test_caregiver_response_contract_get_post_patch(client, db, monkeypatch):
    """APIResponse envelope and Section 10 caregiver fields on all routes."""
    token = _token(client, db, monkeypatch, "+989143003014")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/user/caregivers",
        json={"name": "Contact", "phone": "+989120000014", "relationship": "friend"},
        headers=headers,
    )
    assert created.status_code == 200
    _assert_caregiver_contract(created.json())
    data = created.json()["data"]
    assert data["notify_vital_alerts"] is False
    assert data["emergency_priority"] is None
    assert data["is_active"] is True
    cid = data["id"]

    listed = client.get("/user/caregivers", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["ok"] is True
    caregivers = listed.json()["data"]["caregivers"]
    assert len(caregivers) == 1
    _assert_caregiver_contract({"ok": True, "data": caregivers[0]})

    patched = client.patch(
        f"/user/caregivers/{cid}",
        json={"notify_vital_alerts": True, "emergency_priority": 2},
        headers=headers,
    )
    assert patched.status_code == 200
    _assert_caregiver_contract(patched.json())
    assert patched.json()["data"]["notify_vital_alerts"] is True
    assert patched.json()["data"]["emergency_priority"] == 2

    soft_deleted = client.delete(f"/user/caregivers/{cid}", headers=headers)
    assert soft_deleted.status_code == 200
    active_only = client.get("/user/caregivers", headers=headers).json()["data"]["caregivers"]
    assert active_only == []


def test_caregiver_cross_user_list_denied(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989143003015")
    t2 = _token(client, db, monkeypatch, "+989143003016")
    client.post(
        "/user/caregivers",
        json={"name": "Private", "phone": "+989120000015"},
        headers={"Authorization": f"Bearer {t1}"},
    )
    other_list = client.get("/user/caregivers", headers={"Authorization": f"Bearer {t2}"})
    assert other_list.status_code == 200
    assert other_list.json()["data"]["caregivers"] == []


def test_caregiver_cross_user_patch_denied(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989143003012")
    t2 = _token(client, db, monkeypatch, "+989143003013")
    cid = client.post(
        "/user/caregivers",
        json={"name": "Mom"},
        headers={"Authorization": f"Bearer {t1}"},
    ).json()["data"]["id"]
    assert client.patch(
        f"/user/caregivers/{cid}",
        json={"notify_vital_alerts": True},
        headers={"Authorization": f"Bearer {t2}"},
    ).status_code == 404
