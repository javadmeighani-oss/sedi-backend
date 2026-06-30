"""Gate 2 — habits API."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_habits_requires_auth(client):
    assert client.get("/user/habits").status_code == 401


def test_habits_crud_and_isolation(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989143001001")
    t2 = _token(client, db, monkeypatch, "+989143001002")
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}

    created = client.post("/user/habits", json={"name": "morning walk", "frequency": "daily"}, headers=h1)
    assert created.status_code == 200, created.text
    hid = created.json()["data"]["id"]

    listed = client.get("/user/habits", headers=h1)
    assert listed.status_code == 200
    assert len(listed.json()["data"]["habits"]) == 1

    patched = client.patch(f"/user/habits/{hid}", json={"frequency": "weekly"}, headers=h1)
    assert patched.status_code == 200

    assert client.patch(f"/user/habits/{hid}", json={"name": "hack"}, headers=h2).status_code == 404

    deleted = client.delete(f"/user/habits/{hid}", headers=h1)
    assert deleted.status_code == 200


def test_habits_rejects_user_id_query(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143001003")
    r = client.get("/user/habits?user_id=1", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422
