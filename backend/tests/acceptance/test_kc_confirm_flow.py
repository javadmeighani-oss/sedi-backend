"""
Acceptance test: KC confirm flow (API-driven, no ORM imports).
"""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token

_TEST_USER_ID = 91001


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
        {"id": _TEST_USER_ID, "name": "KC Test", "secret": "x", "lang": "fa"},
    )
    db.commit()
    return _TEST_USER_ID


def test_kc_confirm_flow(client: TestClient, test_user_id: int):
    user_id = test_user_id
    source_id = f"pytest-{uuid.uuid4().hex[:12]}"
    headers = _auth_header(user_id)

    r1 = client.post(
        "/knowledge/extract_from_message",
        json={
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": source_id,
        },
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("ok") is True
    data1 = d1.get("data", {})
    assert set(data1.keys()) >= {"extracted_count", "created_candidates_count", "auto_accepted_count", "ignored_count"}
    assert data1.get("created_candidates_count", 0) >= 1

    r2 = client.get("/knowledge/next_question", headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("ok") is True
    data2 = d2.get("data")
    assert data2 is not None
    assert data2.get("question_type") == "confirm_candidate"
    assert data2.get("candidate_id") is not None
    candidate_id = data2["candidate_id"]

    r3 = client.post(
        "/knowledge/apply_answer",
        json={
            "question_type": "confirm_candidate",
            "candidate_id": candidate_id,
            "answer": "بله",
        },
        headers=headers,
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3.get("ok") is True
    assert d3.get("data", {}).get("applied") == "confirm_accepted"

    r4 = client.get("/knowledge/next_question", headers=headers)
    assert r4.status_code == 200
    d4 = r4.json()
    data4 = d4.get("data")
    if data4 and data4.get("question_type") == "confirm_candidate":
        assert data4.get("candidate_id") != candidate_id


def _make_confirm_candidate(client: TestClient, user_id: int) -> int:
    source_id = f"pytest-{uuid.uuid4().hex[:12]}"
    headers = _auth_header(user_id)
    client.post(
        "/knowledge/extract_from_message",
        json={
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": source_id,
        },
        headers=headers,
    )
    r = client.get("/knowledge/next_question", headers=headers)
    assert r.status_code == 200
    data = r.json().get("data")
    assert data and data.get("question_type") == "confirm_candidate"
    return data["candidate_id"]


def test_apply_answer_with_answer_baleh(client: TestClient, test_user_id: int):
    candidate_id = _make_confirm_candidate(client, test_user_id)
    r = client.post(
        "/knowledge/apply_answer",
        json={
            "candidate_id": candidate_id,
            "question_type": "confirm_candidate",
            "answer": "بله",
        },
        headers=_auth_header(test_user_id),
    )
    assert r.status_code == 200
    assert r.json().get("data", {}).get("applied") == "confirm_accepted"


def test_apply_answer_with_answer_yes(client: TestClient, test_user_id: int):
    candidate_id = _make_confirm_candidate(client, test_user_id)
    r = client.post(
        "/knowledge/apply_answer",
        json={
            "candidate_id": candidate_id,
            "question_type": "confirm_candidate",
            "answer": "yes",
        },
        headers=_auth_header(test_user_id),
    )
    assert r.status_code == 200
    assert r.json().get("data", {}).get("applied") == "confirm_accepted"


def test_apply_answer_with_value_still_works(client: TestClient, test_user_id: int):
    candidate_id = _make_confirm_candidate(client, test_user_id)
    r = client.post(
        "/knowledge/apply_answer",
        json={
            "candidate_id": candidate_id,
            "question_type": "confirm_candidate",
            "value": "بله",
        },
        headers=_auth_header(test_user_id),
    )
    assert r.status_code == 200
    assert r.json().get("data", {}).get("applied") == "confirm_accepted"


def test_apply_answer_with_answer_no_rejects_candidate(client: TestClient, test_user_id: int, db: Session):
    candidate_id = _make_confirm_candidate(client, test_user_id)

    r = client.post(
        "/knowledge/apply_answer",
        json={
            "candidate_id": candidate_id,
            "question_type": "confirm_candidate",
            "answer": "نه",
        },
        headers=_auth_header(test_user_id),
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data", {})
    assert data.get("applied") == "confirm_rejected"

    row = db.execute(
        text("SELECT status FROM kc_fact_candidates WHERE id = :id"),
        {"id": candidate_id},
    ).mappings().first()
    assert row is not None
    assert row["status"] == "rejected"


def test_apply_answer_with_answer_later_skips_candidate(client: TestClient, test_user_id: int, db: Session):
    candidate_id = _make_confirm_candidate(client, test_user_id)

    r = client.post(
        "/knowledge/apply_answer",
        json={
            "candidate_id": candidate_id,
            "question_type": "confirm_candidate",
            "answer": "بعدا",
        },
        headers=_auth_header(test_user_id),
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data", {})
    assert data.get("applied") == "confirm_skipped"

    row = db.execute(
        text("SELECT status FROM kc_fact_candidates WHERE id = :id"),
        {"id": candidate_id},
    ).mappings().first()
    assert row is not None
    assert row["status"] == "pending"
