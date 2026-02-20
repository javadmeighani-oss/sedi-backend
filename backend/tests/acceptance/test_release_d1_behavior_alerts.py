"""
Release D1 Acceptance: Behavior Activation (device_events -> decision_engine -> notifications)

Proves: HR 140 -> notification created with channel=health_alert and dedupe_key format
alert:heart_rate:{user_id}:{minute_bucket}:{rule_id}. Dedupe: same request again within
same minute does NOT create a second notification.
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
def release_d1_user(db: Session) -> User:
    user = db.query(User).filter(User.id == 1).first()
    if user is None:
        user = User(
            id=1,
            name="Release D1 User",
            secret_key="release-d1-secret",
            preferred_language="fa",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def device_auth_legacy(monkeypatch) -> str:
    monkeypatch.setenv("DEVICE_AUTH_MODE", "legacy_only")
    monkeypatch.setenv("DEVICE_INGEST_TOKEN", "release-d1-ingest-token")
    return "release-d1-ingest-token"


def _device_ingest_headers(token: str) -> dict:
    return {"X-DEVICE-TOKEN": token}


def test_d1_hr_140_creates_health_alert_notification(
    client: TestClient,
    db: Session,
    release_d1_user: User,
    device_auth_legacy: str,
) -> None:
    """POST /device/ingest with bpm=140 -> one notification with channel=health_alert and dedupe_key like alert:heart_rate:1:%."""
    response = client.post(
        "/device/ingest",
        json={
            "user_id": release_d1_user.id,
            "device_id": "Sedi001",
            "event_type": "heart_rate",
            "payload": {"bpm": 140, "ts": "2026-02-20T14:30:00Z"},
            "recorded_at": "2026-02-20T14:30:00Z",
        },
        headers=_device_ingest_headers(device_auth_legacy),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("ok") is True
    assert "data" in data
    assert data["data"].get("actions_created", 0) >= 1

    db.expire_all()
    rows = (
        db.query(Notification)
        .filter(
            Notification.user_id == release_d1_user.id,
            Notification.channel == "health_alert",
            Notification.dedupe_key.like("alert:heart_rate:1:%"),
        )
        .all()
    )
    assert len(rows) == 1, f"Expected exactly 1 notification, got {len(rows)}"
    row = rows[0]
    assert row.type == "health_alert"
    assert row.dedupe_key and row.dedupe_key.startswith("alert:heart_rate:1:")
    assert row.body and len(row.body.strip()) > 0


def test_d1_dedupe_same_minute_does_not_create_second_notification(
    client: TestClient,
    db: Session,
    release_d1_user: User,
    device_auth_legacy: str,
) -> None:
    """Same ingest (bpm=140, same minute) sent twice -> only one notification (dedupe)."""
    # Use a distinct minute bucket so we only count notifications from this test
    minute_bucket_str = "202602201500"  # YYYYMMDDHHMM for 2026-02-20 15:00 UTC
    payload = {
        "user_id": release_d1_user.id,
        "device_id": "Sedi001",
        "event_type": "heart_rate",
        "payload": {"bpm": 140, "ts": "2026-02-20T15:00:00Z"},
        "recorded_at": "2026-02-20T15:00:00Z",
    }
    headers = _device_ingest_headers(device_auth_legacy)
    dedupe_prefix = f"alert:heart_rate:1:{minute_bucket_str}:"

    response1 = client.post("/device/ingest", json=payload, headers=headers)
    assert response1.status_code == 200, response1.text
    assert response1.json().get("ok") is True

    db.expire_all()
    count_after_first = (
        db.query(Notification)
        .filter(
            Notification.user_id == release_d1_user.id,
            Notification.channel == "health_alert",
            Notification.dedupe_key.like(dedupe_prefix + "%"),
        )
        .count()
    )
    assert count_after_first == 1, f"After first request expected 1 notification, got {count_after_first}"

    response2 = client.post("/device/ingest", json=payload, headers=headers)
    assert response2.status_code == 200, response2.text
    assert response2.json().get("ok") is True

    db.expire_all()
    count_after_second = (
        db.query(Notification)
        .filter(
            Notification.user_id == release_d1_user.id,
            Notification.channel == "health_alert",
            Notification.dedupe_key.like(dedupe_prefix + "%"),
        )
        .count()
    )
    assert count_after_second == 1, f"Dedupe failed: expected 1 notification after second request, got {count_after_second}"
