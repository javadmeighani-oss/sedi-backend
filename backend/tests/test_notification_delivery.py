"""
Tests for notification delivery outbox: deliver_pending marks is_sent (and sent_at).
"""

import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.app.models import Notification, User
from backend.app.services.notifications.delivery_service import (
    DeliveryService,
    LoggingOnlyAdapter,
)


@pytest.fixture
def test_user(db: Session):
    """Create a test user."""
    user = User(
        id=900,
        name="Delivery Test User",
        secret_key="secret",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user


def test_deliver_pending_marks_is_sent(db: Session, test_user: User):
    """Create notification with is_sent=false; run deliver_pending; assert is_sent=true."""
    notif = Notification(
        user_id=test_user.id,
        type="health_alert",
        title="Test Alert",
        body="Test body",
        priority="high",
        is_read=False,
        is_sent=False,
        sent_at=None,
        dedupe_key="test:900:delivery",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    assert notif.is_sent is False
    assert notif.sent_at is None

    service = DeliveryService(db=db)
    sent_count = service.deliver_pending(limit=100)

    assert sent_count == 1
    db.refresh(notif)
    assert notif.is_sent is True
    assert notif.sent_at is not None


def test_deliver_pending_idempotent(db: Session, test_user: User):
    """Second run of deliver_pending does not resend already-sent notifications."""
    notif = Notification(
        user_id=test_user.id,
        type="health_alert",
        title="Test",
        body="Body",
        priority="normal",
        is_sent=False,
        sent_at=None,
        dedupe_key="test:900:idem",
    )
    db.add(notif)
    db.commit()

    service = DeliveryService(db=db)
    first = service.deliver_pending(limit=100)
    second = service.deliver_pending(limit=100)

    assert first == 1
    assert second == 0


def test_logging_adapter_returns_success(db: Session, test_user: User):
    """Default LoggingOnlyAdapter.send returns True."""
    notif = Notification(
        user_id=test_user.id,
        type="connection_ping",
        title="Ping",
        body="Hello",
        priority="low",
        is_sent=False,
        dedupe_key="test:900:log",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    adapter = LoggingOnlyAdapter()
    result = adapter.send(notif)
    assert result is True


def test_deliver_pending_endpoint(client: TestClient, db: Session, test_user: User, monkeypatch):
    """POST /notifications/deliver_pending processes unsent and returns sent_count."""
    monkeypatch.setenv("ADMIN_TOKEN", "test-deliver-pending-admin")
    notif = Notification(
        user_id=test_user.id,
        type="health_alert",
        title="E2E",
        body="E2E body",
        priority="high",
        is_sent=False,
        dedupe_key="test:900:endpoint",
    )
    db.add(notif)
    db.commit()

    response = client.post(
        "/notifications/deliver_pending?limit=10",
        headers={"X-Admin-Token": "test-deliver-pending-admin"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["sent_count"] == 1
    db.refresh(notif)
    assert notif.is_sent is True


def test_deliver_pending_endpoint_requires_admin_when_token_unset(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    response = client.post("/notifications/deliver_pending?limit=10")
    assert response.status_code == 403
    assert response.json().get("detail") == "admin_disabled"
