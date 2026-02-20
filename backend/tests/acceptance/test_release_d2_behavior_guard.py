"""
Release D2 Acceptance: Behavior Guard (cooldown + skipped_reason).

Two ingest events that would trigger the same rule_id within cooldown:
- First: actions_created=1, notification created.
- Second: actions_created=0, skipped_reason present; notification count unchanged.
"""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models import Notification, User
from backend.tests.test_db_config import get_test_database_url


_BLOCKED_DB_SUBSTRINGS = ("sedi_db", "prod", "production")


def _is_production_db_url(url: str) -> bool:
    u = (url or "").lower()
    return any(blocked in u for blocked in _BLOCKED_DB_SUBSTRINGS)


def _env_indicates_production() -> bool:
    env = (os.environ.get("ENV") or "").lower()
    app_env = (os.environ.get("APP_ENV") or "").lower()
    return env == "production" or app_env == "production"


_test_db_url = get_test_database_url()
if _env_indicates_production():
    raise RuntimeError(
        "Refusing to run acceptance tests: ENV or APP_ENV indicates production."
    )
if _is_production_db_url(_test_db_url):
    raise RuntimeError(
        "Refusing to run acceptance tests against a production-like DB URL. "
        "Set TEST_DATABASE_URL to a safe test database (e.g. sedi_test)."
    )


@pytest.fixture
def release_d2_user(db: Session) -> User:
    user = db.query(User).filter(User.id == 2).first()
    if user is None:
        user = User(
            id=2,
            name="Release D2 User",
            secret_key="release-d2-secret",
            preferred_language="fa",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def device_auth_legacy(monkeypatch) -> str:
    monkeypatch.setenv("DEVICE_AUTH_MODE", "legacy_only")
    monkeypatch.setenv("DEVICE_INGEST_TOKEN", "release-d2-ingest-token")
    return "release-d2-ingest-token"


@pytest.fixture
def short_cooldown(monkeypatch) -> None:
    """Short cooldown so two requests a few seconds apart are within cooldown."""
    monkeypatch.setenv("HEALTH_ALERT_COOLDOWN_SECONDS", "60")


def _device_ingest_headers(token: str) -> dict:
    return {"X-DEVICE-TOKEN": token}


def test_d2_two_ingests_same_rule_within_cooldown_only_one_notification(
    client: TestClient,
    db: Session,
    release_d2_user: User,
    device_auth_legacy: str,
    short_cooldown: None,
) -> None:
    """
    Two ingest events (different 5-min buckets so two device events) that trigger
    same rule_id (heart_rate_high). Second is within D2 cooldown -> only one
    notification; second response has actions_created=0 and skipped_reason.
    """
    headers = _device_ingest_headers(device_auth_legacy)
    user_id = release_d2_user.id

    # First request: bucket 16:00 -> creates device event + notification + guard state
    response1 = client.post(
        "/device/ingest",
        json={
            "user_id": user_id,
            "device_id": "Sedi002",
            "event_type": "heart_rate",
            "payload": {"bpm": 140, "ts": "2026-02-20T16:00:00Z"},
            "recorded_at": "2026-02-20T16:00:00Z",
        },
        headers=headers,
    )
    assert response1.status_code == 200, response1.text
    data1 = response1.json()
    assert data1.get("ok") is True
    assert data1["data"].get("actions_created", 0) == 1, data1

    # Second request: bucket 16:05 (different from 16:00) -> new device event, same rule, guard blocks
    response2 = client.post(
        "/device/ingest",
        json={
            "user_id": user_id,
            "device_id": "Sedi002",
            "event_type": "heart_rate",
            "payload": {"bpm": 140, "ts": "2026-02-20T16:06:00Z"},
            "recorded_at": "2026-02-20T16:06:00Z",
        },
        headers=headers,
    )
    assert response2.status_code == 200, response2.text
    data2 = response2.json()
    assert data2.get("ok") is True
    assert data2["data"].get("actions_created", 0) == 0, data2
    assert "skipped_reason" in data2["data"], data2
    assert data2["data"]["skipped_reason"] == "cooldown", data2

    db.expire_all()
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.channel == "health_alert",
        )
        .count()
    )
    assert count == 1, f"Expected exactly 1 health_alert notification, got {count}"
