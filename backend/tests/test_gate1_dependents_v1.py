"""Gate 1 — dependent (special) users."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app import models
from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_dependent_create_list_patch(client, db, monkeypatch):
    phone = "+989144004001"
    token = _token(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/user/dependents",
        json={
            "name": "Grandma",
            "preferred_language": "fa",
            "birth_year": 1940,
            "relationship": "mother",
            "timezone": "Asia/Tehran",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    dep_id = created.json()["data"]["dependent_user_id"]
    assert created.json()["data"]["account_type"] == "dependent"

    listed = client.get("/user/dependents", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]["dependents"]) == 1

    got = client.get(f"/user/dependents/{dep_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["data"]["name"] == "Grandma"

    patched = client.patch(
        f"/user/dependents/{dep_id}",
        json={"name": "Grandmother", "addressing_preference": "formal"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "Grandmother"

    user = db.query(models.User).filter(models.User.id == dep_id).first()
    assert user.account_type == "dependent"
    assert user.phone is None


def test_caregiver_cannot_access_other_dependent(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989144004002")
    t2 = _token(client, db, monkeypatch, "+989144004003")
    dep_id = client.post(
        "/user/dependents",
        json={"name": "Child"},
        headers={"Authorization": f"Bearer {t1}"},
    ).json()["data"]["dependent_user_id"]
    assert client.get(f"/user/dependents/{dep_id}", headers={"Authorization": f"Bearer {t2}"}).status_code == 404
