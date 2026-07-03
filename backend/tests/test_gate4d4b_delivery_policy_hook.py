"""Gate 4D-4b — delivery-time policy hook tests (no real FCM)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models import Notification, NotificationPrefs, User
from backend.app.services.gate4.feature_flags import (
    gate4_delivery_policy_enabled,
    gate4_delivery_policy_shadow_enabled,
)
from backend.app.services.gate4.policy_resolver import (
    ResolvedNotificationPolicy,
    apply_policy_to_delivery_decision,
    evaluate_delivery_with_gate4_policy,
)
from backend.app.services.gate4.notification_policy import NotificationPolicyDecision
from backend.app.services.notifications.delivery_service import (
    DeliveryService,
    LoggingOnlyAdapter,
)


@pytest.fixture(autouse=True)
def _clear_delivery_flags(monkeypatch):
    monkeypatch.delenv("SEDI_GATE4_DELIVERY_POLICY", raising=False)
    monkeypatch.delenv("SEDI_GATE4_DELIVERY_POLICY_SHADOW", raising=False)
    monkeypatch.delenv("SEDI_GATE4_POLICY_LOG_DECISIONS", raising=False)


def test_delivery_flags_default_false():
    assert gate4_delivery_policy_enabled() is False
    assert gate4_delivery_policy_shadow_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", " Yes ", "ON"])
def test_delivery_flags_parse_true_values(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", value)
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY_SHADOW", value)
    assert gate4_delivery_policy_enabled() is True
    assert gate4_delivery_policy_shadow_enabled() is True


@pytest.fixture
def delivery_user(db):
    user = User(name="Delivery Policy User", secret_key="d4b", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _quiet_prefs(db, user_id: int) -> None:
    db.add(
        NotificationPrefs(
            user_id=user_id,
            quiet_hours_enabled=True,
            quiet_start="22:00",
            quiet_end="08:00",
        )
    )
    db.commit()


class _FixedUtcNow(datetime):
    """Subclass used to pin delivery_service datetime.utcnow() in tests."""

    _fixed: datetime = datetime(2026, 7, 2, 20, 0, 0)

    @classmethod
    def utcnow(cls) -> datetime:
        return cls._fixed


@pytest.fixture
def fixed_quiet_delivery_now(monkeypatch):
    """Pin deliver_pending 'now' to 20:00 UTC (23:30 Asia/Tehran quiet window)."""
    monkeypatch.setattr(
        "backend.app.services.notifications.delivery_service.datetime",
        _FixedUtcNow,
    )


def _pending_notification(
    db,
    user_id: int,
    *,
    priority: str = "normal",
    notif_type: str = "connection_ping",
    dedupe_key: str,
    scheduled_for: datetime | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        type=notif_type,
        title="Test",
        body="Test body",
        priority=priority,
        is_read=False,
        is_sent=False,
        scheduled_for=scheduled_for,
        status="queued",
        channel="engagement",
        dedupe_key=dedupe_key,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def test_flags_off_delivery_helper_returns_deliver_true(db, delivery_user):
    notif = _pending_notification(db, delivery_user.id, dedupe_key="d4b:off:1")
    with patch(
        "backend.app.services.gate4.policy_resolver.resolve_notification_policy"
    ) as mock_resolve:
        should_deliver, decision = evaluate_delivery_with_gate4_policy(
            db, notification=notif
        )
    assert should_deliver is True
    assert decision is None
    mock_resolve.assert_not_called()


def test_shadow_mode_computes_decision_but_delivers(db, delivery_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY_SHADOW", "true")
    _quiet_prefs(db, delivery_user.id)
    notif = _pending_notification(db, delivery_user.id, dedupe_key="d4b:shadow:1")

    now_utc = datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc)
    should_deliver, decision = evaluate_delivery_with_gate4_policy(
        db, notification=notif, now_utc=now_utc
    )
    assert should_deliver is True
    assert decision is not None
    assert decision.should_deliver_now is False


def test_enforce_defers_non_critical_during_quiet(
    db, delivery_user, monkeypatch, fixed_quiet_delivery_now
):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", "true")
    _quiet_prefs(db, delivery_user.id)
    notif = _pending_notification(db, delivery_user.id, dedupe_key="d4b:defer:1")

    fixed_now = _FixedUtcNow.utcnow()

    adapter = MagicMock(spec=LoggingOnlyAdapter)
    adapter.channel = "db_only"
    adapter.send = MagicMock(return_value=True)

    service = DeliveryService(db, adapter=adapter)
    sent_count = service.deliver_pending(limit=10)

    assert sent_count == 0
    adapter.send.assert_not_called()
    db.refresh(notif)
    assert notif.is_sent is False
    assert notif.status == "queued"
    assert notif.status != "failed"
    assert notif.scheduled_for is not None
    assert notif.scheduled_for > fixed_now


def test_deferred_notification_not_marked_failed(
    db, delivery_user, monkeypatch, fixed_quiet_delivery_now
):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", "true")
    _quiet_prefs(db, delivery_user.id)
    notif = _pending_notification(db, delivery_user.id, dedupe_key="d4b:notfailed:1")

    service = DeliveryService(db, adapter=LoggingOnlyAdapter())
    service.deliver_pending(limit=10)

    db.refresh(notif)
    assert notif.is_sent is False
    assert notif.status != "failed"
    assert notif.last_error is None


def test_critical_during_quiet_still_sends(
    db, delivery_user, monkeypatch, fixed_quiet_delivery_now
):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", "true")
    _quiet_prefs(db, delivery_user.id)
    notif = _pending_notification(
        db,
        delivery_user.id,
        priority="critical",
        notif_type="health_alert",
        dedupe_key="d4b:critical:1",
        scheduled_for=None,
    )

    adapter = MagicMock(spec=LoggingOnlyAdapter)
    adapter.channel = "db_only"
    adapter.send = MagicMock(return_value=True)

    service = DeliveryService(db, adapter=adapter)
    sent_count = service.deliver_pending(limit=10)

    assert sent_count == 1
    adapter.send.assert_called_once()
    db.refresh(notif)
    assert notif.is_sent is True


def test_resolver_failure_fails_open(db, delivery_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", "true")
    notif = _pending_notification(db, delivery_user.id, dedupe_key="d4b:failopen:1")

    adapter = MagicMock(spec=LoggingOnlyAdapter)
    adapter.channel = "db_only"
    adapter.send = MagicMock(return_value=True)

    with patch(
        "backend.app.services.gate4.policy_resolver.resolve_notification_policy",
        side_effect=RuntimeError("boom"),
    ):
        service = DeliveryService(db, adapter=adapter)
        sent_count = service.deliver_pending(limit=10)

    assert sent_count == 1
    adapter.send.assert_called_once()


def test_scheduled_for_respected_by_pending_query(
    db, delivery_user, monkeypatch, fixed_quiet_delivery_now
):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", "true")
    _quiet_prefs(db, delivery_user.id)
    notif = _pending_notification(db, delivery_user.id, dedupe_key="d4b:sched:1")

    service = DeliveryService(db, adapter=LoggingOnlyAdapter())
    first = service.deliver_pending(limit=10)
    assert first == 0

    db.refresh(notif)
    future_scheduled = notif.scheduled_for
    assert future_scheduled is not None

    second = service.deliver_pending(limit=10)
    assert second == 0


def test_delivery_service_sent_count_unchanged_when_deferred(
    db, delivery_user, monkeypatch, fixed_quiet_delivery_now
):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", "true")
    _quiet_prefs(db, delivery_user.id)
    _pending_notification(db, delivery_user.id, dedupe_key="d4b:count:1")

    service = DeliveryService(db, adapter=LoggingOnlyAdapter())
    assert service.deliver_pending(limit=10) == 0


def test_apply_policy_to_delivery_never_defers_critical():
    decision = NotificationPolicyDecision(action="defer", reason="quiet_hours", risk_level="critical")
    policy = ResolvedNotificationPolicy(
        decision=decision,
        should_enqueue=True,
        should_deliver_now=False,
        reason_code="quiet_or_sleep_deferred",
        is_quiet_time=True,
    )
    assert (
        apply_policy_to_delivery_decision(
            policy, enforce_enabled=True, risk="critical"
        )
        is True
    )


def test_apply_policy_to_delivery_high_not_critical():
    decision = NotificationPolicyDecision(action="defer", reason="quiet_hours", risk_level="high")
    policy = ResolvedNotificationPolicy(
        decision=decision,
        should_enqueue=True,
        should_deliver_now=False,
        reason_code="quiet_or_sleep_deferred",
        is_quiet_time=True,
    )
    assert (
        apply_policy_to_delivery_decision(policy, enforce_enabled=True, risk="high")
        is False
    )


def test_enforce_skips_do_not_notify_without_sending(db, delivery_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_DELIVERY_POLICY", "true")
    notif = _pending_notification(
        db,
        delivery_user.id,
        priority="do_not_notify",
        dedupe_key="d4b:donot:1",
    )

    adapter = MagicMock(spec=LoggingOnlyAdapter)
    adapter.channel = "db_only"
    adapter.send = MagicMock(return_value=True)

    service = DeliveryService(db, adapter=adapter)
    sent_count = service.deliver_pending(limit=10)

    assert sent_count == 0
    adapter.send.assert_not_called()
    db.refresh(notif)
    assert notif.is_sent is False
    assert notif.status != "failed"
