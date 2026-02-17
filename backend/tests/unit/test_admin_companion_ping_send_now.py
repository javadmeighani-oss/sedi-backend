"""
Unit tests: POST /notifications/admin/companion_ping/send_now (Behavior V1 admin trigger).
- BEHAVIOR_V1_ENABLED=true and outside quiet hours and under budget => created true.
- Second call same day => created false (initiated_today).
"""
from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.database import get_db
from backend.app.main import app

_ADMIN_TOKEN = "test-admin-companion-ping"
_TEST_USER_ID = 70010


@pytest.fixture
def db_session():
    # NOTE: SQLite in-memory creates a NEW database per connection.
    # StaticPool forces a single connection so create_all() and Session share the same DB.
    # check_same_thread=False is required because TestClient may use different threads.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # IMPORTANT: import models BEFORE create_all so all tables are registered on Base.metadata.
    import backend.app.models as m
    Base = m.Base
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user_id(db_session):
    db_session.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, datetime('now'))"
        ),
        {"id": _TEST_USER_ID, "name": "Admin Companion Ping Test", "secret": "x", "lang": "fa"},
    )
    db_session.commit()
    return _TEST_USER_ID


@pytest.fixture
def client_with_db(db_session, test_user_id):
    def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_admin_companion_ping_send_now_created_when_allowed(client_with_db, test_user_id, monkeypatch):
    """When BEHAVIOR_V1_ENABLED=true and outside quiet hours and under budget => created true."""
    monkeypatch.setenv("ADMIN_TOKEN", _ADMIN_TOKEN)
    monkeypatch.setenv("BEHAVIOR_V1_ENABLED", "true")
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        r = client_with_db.post(
            "/notifications/admin/companion_ping/send_now",
            params={"user_id": test_user_id},
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["data"]["created"] is True
    assert data["data"]["notification_id"] is not None
    assert data["data"]["deeplink"] is not None
    assert "companion_ping" in (data["data"].get("deeplink") or "")
    assert data["data"].get("type") == "companion_ping"


def test_admin_companion_ping_send_now_second_call_same_day_created_false(client_with_db, test_user_id, monkeypatch):
    """Second call same day => created false (initiated_today)."""
    monkeypatch.setenv("ADMIN_TOKEN", _ADMIN_TOKEN)
    monkeypatch.setenv("BEHAVIOR_V1_ENABLED", "true")
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        r1 = client_with_db.post(
            "/notifications/admin/companion_ping/send_now",
            params={"user_id": test_user_id},
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
        assert r1.status_code == 200 and r1.json()["data"]["created"] is True
        r2 = client_with_db.post(
            "/notifications/admin/companion_ping/send_now",
            params={"user_id": test_user_id},
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["ok"] is True
    assert data2["data"]["created"] is False
    assert data2["data"]["notification_id"] is None
    assert data2["data"]["deeplink"] is None


def test_admin_companion_ping_send_now_requires_admin_token(client_with_db, test_user_id, monkeypatch):
    """Without X-Admin-Token or wrong token => 401."""
    monkeypatch.setenv("ADMIN_TOKEN", _ADMIN_TOKEN)
    r = client_with_db.post(
        "/notifications/admin/companion_ping/send_now",
        params={"user_id": test_user_id},
    )
    assert r.status_code == 401
