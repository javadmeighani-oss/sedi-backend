"""
Acceptance tests: KC Question Fatigue Control V1 (API-driven, no ORM imports).
"""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token

_TEST_USER_ID = 91002


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def test_user_id(db: Session) -> int:
    db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": _TEST_USER_ID, "name": "KC Fatigue Test", "secret": "y", "lang": "fa"},
    )
    db.commit()
    return _TEST_USER_ID


def _seed_candidate(client: TestClient, user_id: int) -> None:
    source_id = f"pytest-fatigue-{uuid.uuid4().hex[:12]}"
    r = client.post(
        "/knowledge/extract_from_message",
        json={
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": source_id,
        },
        headers=_auth_header(user_id),
    )
    assert r.status_code == 200, r.text
    assert r.json().get("data", {}).get("created_candidates_count", 0) >= 1


def test_kc_next_question_blocked_by_burst_guard(client: TestClient, test_user_id: int):
    user_id = test_user_id
    _seed_candidate(client, user_id)

    r1 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("ok") is True
    data1 = d1.get("data")
    assert data1 is not None, "first call should return a question (confirm_candidate)"
    assert data1.get("question_type") == "confirm_candidate"

    r2 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2.get("ok") is True
    data2 = d2.get("data")
    assert data2 is not None
    assert data2.get("status") == "no_question"
    assert data2.get("reason") == "fatigue_control"
    assert data2.get("next_eligible_at") is not None
    assert "policy" in data2


def test_kc_next_question_blocked_by_daily_cap(client: TestClient, test_user_id: int, monkeypatch):
    monkeypatch.setenv("KC_DAILY_QUESTION_CAP", "1")
    user_id = test_user_id
    _seed_candidate(client, user_id)

    r1 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("ok") is True
    assert d1.get("data") is not None

    r2 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2.get("ok") is True
    data2 = d2.get("data")
    assert data2.get("status") == "no_question"
    assert data2.get("reason") == "fatigue_control"
    policy = data2.get("policy", {})
    assert policy.get("asked_today", 0) >= 1
    assert policy.get("daily_cap") == 1


def test_kc_reject_streak_blocks_until_tomorrow(client: TestClient, test_user_id: int, monkeypatch):
    monkeypatch.setenv("KC_REJECT_STREAK_LIMIT", "2")
    monkeypatch.setenv("KC_BLOCK_UNTIL_HOUR_UTC", "8")
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    user_id = test_user_id

    _seed_candidate(client, user_id)
    r1 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r1.status_code == 200 and r1.json().get("data") is not None
    cand1 = r1.json()["data"]["candidate_id"]
    client.post(
        "/knowledge/apply_answer",
        json={"question_type": "confirm_candidate", "candidate_id": cand1, "answer": "نه"},
        headers=_auth_header(user_id),
    )

    _seed_candidate(client, user_id)
    r2 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r2.status_code == 200 and r2.json().get("data") is not None
    cand2 = r2.json()["data"]["candidate_id"]
    client.post(
        "/knowledge/apply_answer",
        json={"question_type": "confirm_candidate", "candidate_id": cand2, "answer": "no"},
        headers=_auth_header(user_id),
    )

    r3 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r3.status_code == 200, r3.text
    data3 = r3.json().get("data")
    assert data3.get("status") == "no_question"
    assert data3.get("reason") == "fatigue_control"
    next_at = data3.get("next_eligible_at")
    assert next_at is not None
    assert "T08:00:00" in next_at or "T08:00:" in next_at


def test_kc_accept_resets_reject_streak(client: TestClient, test_user_id: int, monkeypatch):
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    user_id = test_user_id

    _seed_candidate(client, user_id)
    r1 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r1.status_code == 200 and r1.json().get("data") is not None
    cand1 = r1.json()["data"]["candidate_id"]
    client.post(
        "/knowledge/apply_answer",
        json={"question_type": "confirm_candidate", "candidate_id": cand1, "answer": "نه"},
        headers=_auth_header(user_id),
    )

    _seed_candidate(client, user_id)
    r2 = client.get("/knowledge/next_question", headers=_auth_header(user_id))
    assert r2.status_code == 200 and r2.json().get("data") is not None
    cand2 = r2.json()["data"]["candidate_id"]
    r_apply = client.post(
        "/knowledge/apply_answer",
        json={"question_type": "confirm_candidate", "candidate_id": cand2, "answer": "بله"},
        headers=_auth_header(user_id),
    )
    assert r_apply.status_code == 200
    data = r_apply.json().get("data", {})
    assert data.get("applied") == "confirm_accepted"
    policy = data.get("policy", {})
    assert policy.get("consecutive_rejects") == 0
