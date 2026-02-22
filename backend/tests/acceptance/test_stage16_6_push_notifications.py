"""
Stage 16.6 Push Notifications v1 Acceptance Tests

Tests:
- push/register upsert works
- queued notification transitions to sent when mock FCM is used (FCM_DISABLED=true)
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models import Notification, PushDevice, User


@pytest.fixture()
def test_user(db: Session) -> User:
    user = User(
        name="Push Test User",
        secret_key="secret",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# Realistic FCM token: >=80 chars, no placeholder words (passes _is_placeholder_or_invalid_fcm_token)
_REGISTER_TEST_FCM_TOKEN = (
    "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuv"
)


def test_push_register_upsert(client: TestClient, db: Session, test_user: User):
    """POST /notifications/push/register upserts by fcm_token; returns device_id."""
    body = {
        "user_id": test_user.id,
        "platform": "android",
        "fcm_token": _REGISTER_TEST_FCM_TOKEN,
        "device_id": "device-abc",
    }
    r1 = client.post("/notifications/push/register", json=body)
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1.get("ok") is True
    assert "device_id" in data1.get("data", {})
    device_id_1 = data1["data"]["device_id"]

    # Upsert: same fcm_token, different user_id (or same) - should update
    body["user_id"] = test_user.id
    body["device_id"] = "device-xyz"
    r2 = client.post("/notifications/push/register", json=body)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2.get("ok") is True
    assert data2["data"].get("device_id") == device_id_1  # same device row
    assert data2["data"].get("updated") is True


def test_queued_to_sent_with_mock_fcm(client: TestClient, db: Session, test_user: User):
    """With FCM_DISABLED=true, a queued notification with active PushDevice transitions to sent."""
    # Register push device (token must pass validation: >=80 chars, no placeholder words)
    device = PushDevice(
        user_id=test_user.id,
        platform="android",
        fcm_token=_REGISTER_TEST_FCM_TOKEN,
        is_active=True,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    # Create queued notification
    notif = Notification(
        user_id=test_user.id,
        type="morning_brief",
        title="Good Morning",
        body="Hello",
        priority="normal",
        is_sent=False,
        sent_at=None,
        status="queued",
        channel="morning",
        dedupe_key="test-stage16-6-mock",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    assert notif.is_sent is False
    assert notif.status == "queued"

    # Run delivery with FCM_DISABLED (mock mode)
    prev = os.environ.get("FCM_DISABLED")
    try:
        os.environ["FCM_DISABLED"] = "true"
        r = client.post("/notifications/deliver_pending?limit=10")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data["data"].get("sent_count") == 1
    finally:
        if prev is not None:
            os.environ["FCM_DISABLED"] = prev
        else:
            os.environ.pop("FCM_DISABLED", None)

    db.refresh(notif)
    assert notif.is_sent is True
    assert notif.sent_at is not None
    assert notif.status == "sent"
