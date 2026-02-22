"""
E2E test: Ingest abnormal heart_rate event → assert health_alert notification is created.

Run locally: pytest -k abnormal_hr
Or: pytest backend/tests/test_e2e_abnormal_hr.py -v
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models import Notification, User


@pytest.fixture
def user_id_1(db: Session):
    """Ensure user with id=1 exists for deterministic E2E."""
    user = db.query(User).filter(User.id == 1).first()
    if user is None:
        user = User(
            id=1,
            name="E2E User",
            secret_key="e2e-secret",
            preferred_language="en",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    yield 1
    # Tables dropped in db fixture teardown; no per-user cleanup needed


@pytest.fixture
def device_auth_legacy(monkeypatch):
    """Use legacy token auth so ingest accepts X-DEVICE-TOKEN without DB device registration."""
    monkeypatch.setenv("DEVICE_AUTH_MODE", "legacy_only")
    monkeypatch.setenv("DEVICE_INGEST_TOKEN", "e2e-test-token")
    return "e2e-test-token"


def test_e2e_abnormal_hr_creates_health_alert(
    client: TestClient,
    db: Session,
    user_id_1: int,
    device_auth_legacy: str,
):
    """
    POST abnormal heart_rate (bpm=180) to /device/ingest;
    assert HTTP 200 and that a health_alert Notification row exists for user_id=1.
    """
    response = client.post(
        "/device/ingest",
        json={
            "user_id": user_id_1,
            "device_id": "Sedi001",
            "event_type": "heart_rate",
            "payload": {"bpm": 180},
            "recorded_at": "2026-02-06T12:00:00Z",
        },
        headers={"X-DEVICE-TOKEN": device_auth_legacy},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("ok") is True, data
    assert "data" in data
    assert data["data"].get("event_id") is not None or "dedupe_key" in data["data"]

    # Assert at least one health_alert notification was created for this user
    db.expire_all()  # Ensure we see committed data from the request's session
    notifications = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id_1,
            Notification.type == "health_alert",
        )
        .all()
    )
    assert len(notifications) >= 1, (
        f"Expected at least one health_alert for user_id={user_id_1}, got {len(notifications)}"
    )
    notif = notifications[0]
    assert notif.body is not None and len(notif.body.strip()) > 0
    assert notif.priority in ("high", "critical")
    # V1: body may be Persian (e.g. "ضربان قلبت بالاست"); dedupe_key may contain heart_rate_high or high_heart_rate
    body_lower = notif.body.lower()
    dedupe = notif.dedupe_key or ""
    assert (
        "heart" in body_lower
        or "ضربان" in notif.body
        or "قلب" in notif.body
        or "heart_rate_high" in dedupe
        or "high_heart_rate" in dedupe
    ), f"Expected heart-related body or dedupe_key; got body={notif.body[:80]!r} dedupe_key={dedupe!r}"
