"""Gate 2 — goals and restrictions APIs."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_goals_crud(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143002001")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/user/goals", json={"category": "health", "title": "lose weight"}, headers=headers)
    assert r.status_code == 200
    gid = r.json()["data"]["id"]
    assert client.get("/user/goals", headers=headers).json()["data"]["goals"][0]["title"] == "lose weight"
    assert client.delete(f"/user/goals/{gid}", headers=headers).status_code == 200


def test_restrictions_crud(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143002002")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/user/restrictions",
        json={"restriction_type": "diet", "title": "low sodium"},
        headers=headers,
    )
    assert r.status_code == 200
    rid = r.json()["data"]["id"]
    assert client.patch(f"/user/restrictions/{rid}", json={"severity": "high"}, headers=headers).status_code == 200
    assert client.delete(f"/user/restrictions/{rid}", headers=headers).status_code == 200
