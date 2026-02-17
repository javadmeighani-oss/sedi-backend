"""
Contract test: GET /knowledge/next_question never returns {"ok": true, "data": null}.
When engine has no question (full profile + care facts, no pending confirm candidate),
response must be data.status == "no_question", data.reason == "no_available_question".
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app as sedi_app

_CONTRACT_TEST_USER_ID = 2


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
def full_profile_user(db: Session) -> int:
    """Seed user_id=2 with full user_profile_core and kc_user_facts (CARE_FACT_TYPES + sleep_window).
    No pending kc_fact_candidates with needs_confirmation -> engine returns None -> API returns no_question.
    """
    uid = _CONTRACT_TEST_USER_ID
    db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": uid, "name": "Contract Test User", "secret": "c", "lang": "fa"},
    )
    db.commit()

    db.execute(
        text(
            "INSERT INTO user_profile_core (user_id, birth_year, sex, height_cm, weight_kg, language, quiet_start, quiet_end, created_at, updated_at) "
            "VALUES (:uid, 1990, 'مرد', 175, 70.0, 'fa', '22:00:00', '06:00:00', NOW(), NOW())"
        ),
        {"uid": uid},
    )
    db.commit()

    now_utc = datetime.utcnow()
    for fact_type, value in [
        ("sleep_window", '"22-6"'),
        ("sleep_quality", '"good"'),
        ("medications_list", '"none"'),
        ("activity_level", '"medium"'),
        ("stress_level", '"low"'),
    ]:
        db.execute(
            text(
                "INSERT INTO kc_user_facts (user_id, fact_type, value_json, verified_by, valid_from, valid_to, created_at, updated_at) "
                "VALUES (:uid, :ft, :val, 'user', :valid_from, NULL, :valid_from, :valid_from)"
            ),
            {"uid": uid, "ft": fact_type, "val": value, "valid_from": now_utc},
        )
    db.commit()
    return uid


def test_next_question_never_data_null_when_no_available_question(client: TestClient, full_profile_user: int):
    """
    User has full profile_core + kc_user_facts for CARE_FACT_TYPES; no pending confirm candidate.
    GET /knowledge/next_question must return data != null and data.status == "no_question".
    """
    user_id = full_profile_user
    r = client.get(f"/knowledge/next_question?user_id={user_id}&lang=fa")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("data") is not None, "contract: data must never be null"
    data = body["data"]
    assert data.get("status") == "no_question"
    assert data.get("reason") == "no_available_question"
    assert "policy" in data
