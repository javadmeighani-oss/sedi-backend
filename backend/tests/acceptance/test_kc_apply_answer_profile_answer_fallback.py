"""
Acceptance test: KC apply_answer for profile fields should accept `answer` when `value` is missing.
Regression: previously /knowledge/apply_answer ignored payload.answer for profile/fact and only used payload.value.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

_TEST_USER_ID = 91002


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
            "user_id": test_user_id,
            "question_id": "kc_q_birth_year_v1",
            "field_key": "birth_year",
            "answer": "1990",  # IMPORTANT: no `value`
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("data", {}).get("applied") == "profile"

    row = db.execute(
        text("SELECT birth_year FROM user_profile_core WHERE user_id = :uid"),
        {"uid": test_user_id},
    ).mappings().first()

    # ensure_profile_core should have created it and birth_year must be set
    assert row is not None
    assert row["birth_year"] == 1990
