"""Fail-closed I10 provider-delivery gate (SEDI_NOTIFICATION_PROVIDER_DELIVERY_ENABLED)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

from backend.app.models import Notification, PushDevice, User
from backend.app.services.notifications.delivery_service import (
    DeliveryService,
    provider_delivery_enabled,
)

_GATE = "SEDI_NOTIFICATION_PROVIDER_DELIVERY_ENABLED"


class CountingAdapter:
    channel = "probe"

    def __init__(self):
        self.calls = 0

    def send(self, notification: Notification) -> bool:
        self.calls += 1
        notification.provider = self.channel
        notification.is_sent = True
        notification.status = "sent"
        notification.sent_at = datetime.utcnow()
        notification.last_error = None
        return True


def _user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _queued(db, user: User, *, body: str = "queued-body") -> Notification:
    n = Notification(
        user_id=user.id,
        type="reminder",
        title="Gate",
        body=body,
        priority="normal",
        is_read=False,
        is_sent=False,
        status="queued",
        sent_at=None,
        provider=None,
        last_error=None,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _device(db, user: User) -> PushDevice:
    d = PushDevice(
        user_id=user.id,
        platform="android",
        fcm_token=("fcm-gate-" + "x" * 80)[:96],
        device_id="install-gate",
        is_active=True,
        last_seen_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _snap_notif(n: Notification) -> dict:
    return {
        "id": n.id,
        "is_sent": n.is_sent,
        "sent_at": n.sent_at,
        "status": n.status,
        "provider": n.provider,
        "last_error": n.last_error,
        "provider_message_id": n.provider_message_id,
        "body": n.body,
    }


def _snap_device(d: PushDevice) -> dict:
    return {
        "id": d.id,
        "is_active": d.is_active,
        "fcm_token": d.fcm_token,
        "device_id": d.device_id,
        "updated_at": d.updated_at,
        "last_seen_at": d.last_seen_at,
    }


def _assert_immutable(db, notif: Notification, before_n: dict, device: PushDevice, before_d: dict):
    db.expire_all()
    after_n = _snap_notif(db.query(Notification).filter(Notification.id == notif.id).one())
    after_d = _snap_device(db.query(PushDevice).filter(PushDevice.id == device.id).one())
    assert after_n == before_n
    assert after_d == before_d
    assert db.query(Notification).filter(Notification.user_id == notif.user_id).count() == 1
    assert db.query(PushDevice).filter(PushDevice.user_id == device.user_id).count() == 1


def test_provider_delivery_enabled_default_unset_is_false(monkeypatch):
    monkeypatch.delenv(_GATE, raising=False)
    assert provider_delivery_enabled() is False


def test_default_unset_deliver_pending_noop_no_db_mutation(db, monkeypatch):
    monkeypatch.delenv(_GATE, raising=False)
    u = _user(db, "GateUnset")
    n = _queued(db, u)
    d = _device(db, u)
    before_n, before_d = _snap_notif(n), _snap_device(d)
    adapter = CountingAdapter()
    sent = DeliveryService(db=db, adapter=adapter).deliver_pending(limit=10)
    assert sent == 0
    assert adapter.calls == 0
    _assert_immutable(db, n, before_n, d, before_d)


def test_explicit_false_deliver_pending_noop_no_db_mutation(db, monkeypatch):
    monkeypatch.setenv(_GATE, "false")
    u = _user(db, "GateFalse")
    n = _queued(db, u)
    d = _device(db, u)
    before_n, before_d = _snap_notif(n), _snap_device(d)
    adapter = CountingAdapter()
    sent = DeliveryService(db=db, adapter=adapter).deliver_pending(limit=10)
    assert sent == 0
    assert adapter.calls == 0
    _assert_immutable(db, n, before_n, d, before_d)


def test_explicit_true_preserves_existing_delivery_path(db, monkeypatch):
    monkeypatch.setenv(_GATE, "true")
    u = _user(db, "GateTrue")
    n = _queued(db, u)
    adapter = CountingAdapter()
    sent = DeliveryService(db=db, adapter=adapter).deliver_pending(limit=10)
    assert sent == 1
    assert adapter.calls == 1
    db.refresh(n)
    assert n.is_sent is True
    assert n.status == "sent"
    assert n.provider == "probe"
    assert n.sent_at is not None


def test_configured_fcm_env_gate_false_selects_no_adapter(db, monkeypatch):
    monkeypatch.setenv(_GATE, "false")
    monkeypatch.setenv("FCM_DISABLED", "false")
    monkeypatch.setenv("FCM_PROJECT_ID", "sedi-test-project")
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT_JSON", "/run/secrets/fcm-service-account.json")
    u = _user(db, "GateFcmMounted")
    n = _queued(db, u)
    d = _device(db, u)
    before_n, before_d = _snap_notif(n), _snap_device(d)
    sentinel = Mock(side_effect=AssertionError("_default_adapter must not run when gate is false"))
    monkeypatch.setattr(
        "backend.app.services.notifications.delivery_service._default_adapter",
        sentinel,
    )
    svc = DeliveryService(db=db)
    assert svc._adapter is None
    sent = svc.deliver_pending(limit=10)
    assert sent == 0
    sentinel.assert_not_called()
    _assert_immutable(db, n, before_n, d, before_d)


def test_http_style_delivery_service_call_gate_false_no_provider(db, monkeypatch):
    monkeypatch.setenv(_GATE, "false")
    u = _user(db, "GateHttp")
    n = _queued(db, u)
    d = _device(db, u)
    before_n, before_d = _snap_notif(n), _snap_device(d)
    # Same construction as scheduler / POST /notifications/deliver_pending.
    sent = DeliveryService(db=db).deliver_pending(limit=10)
    assert sent == 0
    _assert_immutable(db, n, before_n, d, before_d)
