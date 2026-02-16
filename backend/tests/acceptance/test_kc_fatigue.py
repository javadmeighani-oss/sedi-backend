"""
Acceptance tests: KC Question Fatigue Control V1 (API-driven, no ORM imports).
- Burst guard blocks second next_question when called twice quickly.
- Daily cap blocks after N questions (cap=1 in test).
- Reject streak blocks until next day 08:00 UTC after 2 consecutive reject/skip.
- Accept resets consecutive_rejects.
"""

from __future__ import annotations

import uuid
from pathlib import Path
import sys

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app as sedi_app

_TEST_USER_ID = 91002


def _collect_paths(routes, prefix=""):
    paths = set()
    for r in routes:
        path = getattr(r, "path", None) or ""
        if hasattr(r, "routes"):
            paths.update(_collect_paths(r.routes, prefix + path))
        elif path:
            paths.add(prefix + path)
    return paths


@pytest.fixture()
def client() -> TestClient:
    paths = _collect_paths(sedi_app.routes)
    assert "/knowledge/next_question" in paths
    assert "/knowledge/apply_answer" in paths
    assert "/knowledge/extract_from_message" in paths
    return TestClient(sedi_app)


@pytest.fixture()
def db() -> Session:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


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
            "user_id": user_id,
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": source_id,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("data", {}).get("created_candidates_count", 0) >= 1


def test_kc_next_question_blocked_by_burst_guard(client: TestClient, test_user_id: int):
    """Call next_question twice quickly; second returns status=no_question reason=fatigue_control."""
    user_id = test_user_id
    _seed_candidate(client, user_id)

    r1 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("ok") is True
    data1 = d1.get("data")
    assert data1 is not None, "first call should return a question (confirm_candidate)"
    assert data1.get("question_type") == "confirm_candidate"

    r2 = client.get(f"/knowledge/next_question?user_id={user_id}")
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
    """With cap=1, first question succeeds; second next_question is blocked by daily cap."""
    monkeypatch.setenv("KC_DAILY_QUESTION_CAP", "1")
    user_id = test_user_id
    _seed_candidate(client, user_id)

    r1 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("ok") is True
    assert d1.get("data") is not None

    r2 = client.get(f"/knowledge/next_question?user_id={user_id}")
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
    """Two consecutive rejections (e.g. 'نه') trigger block until next day 08:00 UTC."""
    monkeypatch.setenv("KC_REJECT_STREAK_LIMIT", "2")
    monkeypatch.setenv("KC_BLOCK_UNTIL_HOUR_UTC", "8")
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    user_id = test_user_id

    # First candidate: get question, reject
    _seed_candidate(client, user_id)
    r1 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r1.status_code == 200 and r1.json().get("data") is not None
    cand1 = r1.json()["data"]["candidate_id"]
    client.post(
        "/knowledge/apply_answer",
        json={"user_id": user_id, "question_type": "confirm_candidate", "candidate_id": cand1, "answer": "نه"},
    )

    # Second candidate: get question, reject
    _seed_candidate(client, user_id)
    r2 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r2.status_code == 200 and r2.json().get("data") is not None
    cand2 = r2.json()["data"]["candidate_id"]
    client.post(
        "/knowledge/apply_answer",
        json={"user_id": user_id, "question_type": "confirm_candidate", "candidate_id": cand2, "answer": "no"},
    )

    # Next question should be blocked; next_eligible_at should be next day 08:00 UTC
    r3 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r3.status_code == 200, r3.text
    data3 = r3.json().get("data")
    assert data3.get("status") == "no_question"
    assert data3.get("reason") == "fatigue_control"
    next_at = data3.get("next_eligible_at")
    assert next_at is not None
    # Assert hour is 08:00 UTC (format: ISO with time)
    assert "T08:00:00" in next_at or "T08:00:" in next_at


def test_kc_accept_resets_reject_streak(client: TestClient, test_user_id: int, monkeypatch):
    """Reject once then accept; policy should show consecutive_rejects=0."""
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    user_id = test_user_id

    _seed_candidate(client, user_id)
    r1 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r1.status_code == 200 and r1.json().get("data") is not None
    cand1 = r1.json()["data"]["candidate_id"]
    client.post(
        "/knowledge/apply_answer",
        json={"user_id": user_id, "question_type": "confirm_candidate", "candidate_id": cand1, "answer": "نه"},
    )

    _seed_candidate(client, user_id)
    r2 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r2.status_code == 200 and r2.json().get("data") is not None
    cand2 = r2.json()["data"]["candidate_id"]
    r_apply = client.post(
        "/knowledge/apply_answer",
        json={"user_id": user_id, "question_type": "confirm_candidate", "candidate_id": cand2, "answer": "بله"},
    )
    assert r_apply.status_code == 200
    data = r_apply.json().get("data", {})
    assert data.get("applied") == "confirm_accepted"
    policy = data.get("policy", {})
    assert policy.get("consecutive_rejects") == 0
