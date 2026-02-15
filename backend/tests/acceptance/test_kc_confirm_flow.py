"""
Acceptance test: KC confirm flow.
- POST /knowledge/extract_from_message with medium-confidence (stress_level low = 0.75)
- GET /knowledge/next_question returns type=confirm_candidate with candidate_id
- POST /knowledge/apply_answer with Yes => candidate accepted, removed from queue
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import User, KcFactCandidate, KcUserFact


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


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
def test_user(db: Session) -> User:
    user = User(
        name="KC Confirm Test",
        secret_key="secret",
        preferred_language="fa",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_kc_confirm_flow(client: TestClient, db: Session, test_user: User):
    """Full flow: extract (medium conf) -> next_question (confirm) -> apply Yes -> accepted."""
    user_id = test_user.id

    # 1) Extract from message: "استرس ندارم" => stress_level low @ 0.75 (CONFIRM threshold)
    r1 = client.post(
        "/knowledge/extract_from_message",
        json={"user_id": user_id, "text": "استرس ندارم", "language": "fa"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1.get("ok") is True
    data1 = d1.get("data", {})
    assert data1.get("created_candidates_count", 0) >= 1

    # 2) GET next_question returns confirm_candidate
    r2 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("ok") is True
    data2 = d2.get("data")
    assert data2 is not None
    assert data2.get("question_type") == "confirm_candidate"
    assert "candidate_id" in data2
    candidate_id = data2["candidate_id"]

    # 3) Apply answer Yes
    r3 = client.post(
        "/knowledge/apply_answer",
        json={
            "user_id": user_id,
            "candidate_id": candidate_id,
            "question_type": "confirm_candidate",
            "value": "بله، درسته",
        },
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3.get("ok") is True
    assert d3.get("data", {}).get("applied") == "confirm_accepted"

    # 4) next_question no longer returns this candidate (it's accepted)
    r4 = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r4.status_code == 200
    d4 = r4.json()
    data4 = d4.get("data")
    # Should NOT be confirm_candidate for same fact (candidate was accepted)
    if data4 and data4.get("question_type") == "confirm_candidate":
        assert data4.get("candidate_id") != candidate_id


def _make_confirm_candidate(client: TestClient, user_id: int) -> int:
    """Extract from message, get next_question, return candidate_id."""
    client.post("/knowledge/extract_from_message", json={"user_id": user_id, "text": "استرس ندارم", "language": "fa"})
    r = client.get(f"/knowledge/next_question?user_id={user_id}")
    assert r.status_code == 200
    data = r.json().get("data")
    assert data and data.get("question_type") == "confirm_candidate"
    return data["candidate_id"]


def test_apply_answer_with_answer_baleh(client: TestClient, db: Session, test_user: User):
    """apply_answer with {\"answer\": \"بله\"} => confirm_accepted."""
    user_id = test_user.id
    candidate_id = _make_confirm_candidate(client, user_id)
    r = client.post(
        "/knowledge/apply_answer",
        json={"user_id": user_id, "candidate_id": candidate_id, "question_type": "confirm_candidate", "answer": "بله"},
    )
    assert r.status_code == 200
    assert r.json().get("data", {}).get("applied") == "confirm_accepted"


def test_apply_answer_with_answer_yes(client: TestClient, db: Session, test_user: User):
    """apply_answer with {\"answer\": \"yes\"} => confirm_accepted."""
    user_id = test_user.id
    candidate_id = _make_confirm_candidate(client, user_id)
    r = client.post(
        "/knowledge/apply_answer",
        json={"user_id": user_id, "candidate_id": candidate_id, "question_type": "confirm_candidate", "answer": "yes"},
    )
    assert r.status_code == 200
    assert r.json().get("data", {}).get("applied") == "confirm_accepted"


def test_apply_answer_with_value_still_works(client: TestClient, db: Session, test_user: User):
    """apply_answer with {\"value\": \"بله\"} still works."""
    user_id = test_user.id
    candidate_id = _make_confirm_candidate(client, user_id)
    r = client.post(
        "/knowledge/apply_answer",
        json={"user_id": user_id, "candidate_id": candidate_id, "question_type": "confirm_candidate", "value": "بله"},
    )
    assert r.status_code == 200
    assert r.json().get("data", {}).get("applied") == "confirm_accepted"
