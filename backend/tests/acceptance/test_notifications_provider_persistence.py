"""
Regression tests: notification delivery behavior — provider and status persistence.

- LoggingOnlyAdapter path (FCM_DISABLED/db_only): provider=db_only, status=sent, sent_at set.
- Success path: provider set from adapter.channel (e.g. fcm), status=sent.
- Failure path: provider set from adapter.channel, status=failed, last_error set.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy.orm import Session

from backend.app.models import Notification, User
from backend.app.services.notifications.delivery_service import DeliveryService


@pytest.fixture()
def test_user(db: Session) -> User:
    user = User(
        name="Provider Persistence Test User",
        secret_key="secret",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_queued_notification(db: Session, user_id: int, dedupe_key: str = "test-regression") -> Notification:
    notif = Notification(
        user_id=user_id,
        type="morning_brief",
        title="Test",
        body="Body",
        priority="normal",
        is_sent=False,
        sent_at=None,
        status="queued",
        channel="morning",
        dedupe_key=dedupe_key,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def test_logging_only_adapter_sets_provider_db_only_and_sent(db: Session, test_user: User):
    """
    LoggingOnlyAdapter path (FCM_DISABLED/db_only): after deliver_pending(),
    provider is db_only, status is sent, sent_at is set.
    """
    notif = _make_queued_notification(db, test_user.id, "test-db-only")
    assert notif.provider is None
    assert notif.status == "queued"
    assert notif.sent_at is None

    prev = os.environ.get("FCM_DISABLED")
    try:
        os.environ["FCM_DISABLED"] = "true"
        service = DeliveryService(db)
        n = service.deliver_pending(limit=10)
        assert n == 1
    finally:
        if prev is not None:
            os.environ["FCM_DISABLED"] = prev
        else:
            os.environ.pop("FCM_DISABLED", None)

    db.refresh(notif)
    assert notif.provider is not None
    assert notif.provider == "db_only"
    assert notif.status == "sent"
    assert notif.sent_at is not None


def test_success_path_sets_provider_from_adapter_channel(db: Session, test_user: User):
    """
    Success path: adapter with channel='fcm' returns success; after deliver_pending(),
    provider == 'fcm' and status == 'sent'.
    """

    class FakeAdapter:
        channel = "fcm"

        def send(self, notification: Notification) -> bool:
            return True

    notif = _make_queued_notification(db, test_user.id, "test-fake-fcm-ok")
    service = DeliveryService(db, adapter=FakeAdapter())
    n = service.deliver_pending(limit=10)
    assert n == 1

    db.refresh(notif)
    assert notif.provider == "fcm"
    assert notif.status == "sent"


def test_failure_path_persists_provider_and_sets_status_failed(db: Session, test_user: User):
    """
    Failure path: adapter channel='fcm' but send() raises; after deliver_pending(),
    provider == 'fcm', status == 'failed', last_error non-empty.
    """

    class FakeAdapter:
        channel = "fcm"

        def send(self, notification: Notification) -> bool:
            raise Exception("boom")

    notif = _make_queued_notification(db, test_user.id, "test-fake-fcm-fail")
    service = DeliveryService(db, adapter=FakeAdapter())
    n = service.deliver_pending(limit=10)
    assert n == 0

    db.refresh(notif)
    assert notif.provider == "fcm"
    assert notif.status == "failed"
    assert notif.last_error is not None and len(notif.last_error.strip()) > 0
