"""
Acceptance test: KC apply_answer for profile fields should accept `answer` when `value` is missing.
"""

from __future__ import annotations

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
        {"id": _TEST_USER_ID, "name": "KC Profile Test", "secret": "x", "lang": "fa"},
    )
    db.commit()
    return _TEST_USER_ID


def test_apply_answer_profile_birth_year_accepts_answer_field(client: TestClient, db: Session, test_user_id: int):
    r = client.post(
        "/knowledge/apply_answer",
        json={
            "field_key": "birth_year",
            "answer": "1990",
        },
        headers=_auth_header(test_user_id),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("data", {}).get("applied") == "profile"

    row = db.execute(
        text("SELECT birth_year FROM user_profile_core WHERE user_id = :uid"),
        {"uid": test_user_id},
    ).mappings().first()

    assert row is not None
    assert row["birth_year"] == 1990
