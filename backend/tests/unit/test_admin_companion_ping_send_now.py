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
from sqlalchemy import text

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

_ADMIN_TOKEN = "test-admin-companion-ping"
_TEST_USER_ID = 70010


@pytest.fixture
def test_user_id(db):
    db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": _TEST_USER_ID, "name": "Admin Companion Ping Test", "secret": "x", "lang": "fa"},
    )
    db.commit()
    return _TEST_USER_ID


def test_admin_companion_ping_send_now_created_when_allowed(client, test_user_id, monkeypatch):
    """When BEHAVIOR_V1_ENABLED=true and outside quiet hours and under budget => created true."""
    monkeypatch.setenv("ADMIN_TOKEN", _ADMIN_TOKEN)
    monkeypatch.setenv("BEHAVIOR_V1_ENABLED", "true")
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        r = client.post(
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


def test_admin_companion_ping_send_now_second_call_same_day_created_false(client, test_user_id, monkeypatch):
    """Second call same day => created false (initiated_today)."""
    monkeypatch.setenv("ADMIN_TOKEN", _ADMIN_TOKEN)
    monkeypatch.setenv("BEHAVIOR_V1_ENABLED", "true")
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        r1 = client.post(
            "/notifications/admin/companion_ping/send_now",
            params={"user_id": test_user_id},
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
        assert r1.status_code == 200 and r1.json()["data"]["created"] is True
        r2 = client.post(
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


def test_admin_companion_ping_send_now_requires_admin_token(client, test_user_id, monkeypatch):
    """Without X-Admin-Token or wrong token => 401."""
    monkeypatch.setenv("ADMIN_TOKEN", _ADMIN_TOKEN)
    r = client.post(
        "/notifications/admin/companion_ping/send_now",
        params={"user_id": test_user_id},
    )
    assert r.status_code == 401
