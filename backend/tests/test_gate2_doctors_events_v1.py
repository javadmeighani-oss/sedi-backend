"""Gate 2 — doctors, unified events (medical + general deadlines)."""

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


def test_doctors_and_medical_event(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003001")
    headers = {"Authorization": f"Bearer {token}"}
    doc = client.post("/user/doctors", json={"name": "Dr. Heart", "specialty": "cardiology"}, headers=headers)
    assert doc.status_code == 200
    doctor_id = doc.json()["data"]["id"]
    starts = (datetime.utcnow() + timedelta(days=3)).isoformat()
    ev = client.post(
        "/user/events",
        json={
            "title": "Cardiology visit",
            "event_domain": "medical",
            "event_type": "doctor_visit",
            "starts_at": starts,
            "doctor_id": doctor_id,
        },
        headers=headers,
    )
    assert ev.status_code == 200
    assert ev.json()["data"]["event_type"] == "doctor_visit"


def test_work_meeting_event(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003002")
    headers = {"Authorization": f"Bearer {token}"}
    starts = (datetime.utcnow() + timedelta(days=1)).isoformat()
    ev = client.post(
        "/user/events",
        json={
            "title": "Team sync",
            "event_domain": "work",
            "event_type": "work_meeting",
            "starts_at": starts,
        },
        headers=headers,
    )
    assert ev.status_code == 200
    listed = client.get("/user/events", headers=headers)
    assert listed.status_code == 200
    assert any(e["event_domain"] == "work" for e in listed.json()["data"]["events"])


def test_events_cross_user_isolation(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989143003003")
    t2 = _token(client, db, monkeypatch, "+989143003004")
    starts = (datetime.utcnow() + timedelta(days=2)).isoformat()
    created = client.post(
        "/user/events",
        json={"title": "Exam", "event_domain": "education", "event_type": "exam", "starts_at": starts},
        headers={"Authorization": f"Bearer {t1}"},
    )
    eid = created.json()["data"]["id"]
    assert client.patch(f"/user/events/{eid}", json={"title": "hack"}, headers={"Authorization": f"Bearer {t2}"}).status_code == 404
