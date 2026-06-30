"""Gate 2 — minimal Persian event extraction patterns."""

import json
import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services.knowledge.conversation_extractor_v1 import extract_candidates
from backend.app.services.candidate_promotion_service import promote_kc_candidate
from backend.app.services.knowledge.service import create_candidate, accept_candidate
from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_persian_event_extraction_patterns():
    cases = [
        ("فردا ساعت ۱۰ جلسه کاری دارم", "work", "work_meeting"),
        ("جمعه امتحان دارم", "education", "exam"),
        ("هفته بعد تولد مادرم است", "family", "birthday"),
        ("سه‌شنبه آزمایش خون دارم", "medical", "lab_test"),
        ("ماه بعد جراحی دارم", "medical", "surgery"),
        ("نوبت دکتر قلب دارم", "medical", "doctor_visit"),
    ]
    for text, domain, etype in cases:
        found = extract_candidates(text, "fa")
        events = [c for c in found if c.fact_key == "user_event"]
        assert events, f"no user_event for: {text}"
        val = events[0].fact_value
        assert val.get("event_domain") == domain, text
        assert val.get("event_type") == etype, text


def test_persian_event_promotes_to_user_events(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005001")
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/auth/me", headers=headers).json()["data"]["user_id"]
    text = "سه‌شنبه آزمایش خون دارم"
    extracted = extract_candidates(text, "fa")
    ev = next(c for c in extracted if c.fact_key == "user_event")
    cand = create_candidate(
        db=db,
        user_id=user_id,
        source="chat_extraction_v1",
        fact_type=ev.fact_key,
        value_json=json.dumps(ev.fact_value, ensure_ascii=False),
        confidence=ev.confidence,
    )
    accept_candidate(db, cand.id, verified_by="user")
    db.refresh(cand)
    result = promote_kc_candidate(db, cand)
    assert result["target"] == "user_events"
    listed = client.get("/user/events", headers=headers).json()["data"]["events"]
    assert any(e["event_type"] == "lab_test" for e in listed)


def test_lifestyle_event_not_user_event_table(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005002")
    headers = {"Authorization": f"Bearer {token}"}
    le = client.post(
        "/user/lifestyle-events",
        json={"event_type": "mood_log", "value": {"mood": "happy"}, "occurred_at": "2026-06-29T10:00:00"},
        headers=headers,
    )
    assert le.status_code == 200
    events = client.get("/user/events", headers=headers).json()["data"]["events"]
    assert not any(e.get("event_type") == "mood_log" for e in events)


def test_knowledge_mirror_idempotent_goals(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005003")
    headers = {"Authorization": f"Bearer {token}"}
    body = {"goals_json": json.dumps(["کاهش وزن", "خواب بهتر"])}
    assert client.put("/user/knowledge", json=body, headers=headers).status_code == 200
    assert client.put("/user/knowledge", json=body, headers=headers).status_code == 200
    goals = client.get("/user/goals", headers=headers).json()["data"]["goals"]
    titles = [g["title"] for g in goals]
    assert titles.count("کاهش وزن") == 1
    assert titles.count("خواب بهتر") == 1


def test_knowledge_mirror_idempotent_constraints(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005004")
    headers = {"Authorization": f"Bearer {token}"}
    body = {"constraints_json": json.dumps(["بدون نمک", "کم‌چرب"])}
    assert client.put("/user/knowledge", json=body, headers=headers).status_code == 200
    assert client.put("/user/knowledge", json=body, headers=headers).status_code == 200
    restrictions = client.get("/user/restrictions", headers=headers).json()["data"]["restrictions"]
    titles = [r["title"] for r in restrictions]
    assert titles.count("بدون نمک") == 1
    assert titles.count("کم‌چرب") == 1
    # Case-insensitive dedupe: second PUT with different casing must not duplicate.
    body_case = {"constraints_json": json.dumps(["بدون نمک", "کم‌چرب", "No Dairy"])}
    assert client.put("/user/knowledge", json=body_case, headers=headers).status_code == 200
    body_case_repeat = {"constraints_json": json.dumps(["بدون نمک", "کم‌چرب", "no dairy"])}
    assert client.put("/user/knowledge", json=body_case_repeat, headers=headers).status_code == 200
    restrictions = client.get("/user/restrictions", headers=headers).json()["data"]["restrictions"]
    dairy_titles = [r["title"] for r in restrictions if r["title"].strip().lower() == "no dairy"]
    assert len(dairy_titles) == 1
