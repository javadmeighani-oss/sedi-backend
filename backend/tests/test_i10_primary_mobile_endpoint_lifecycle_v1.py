"""I10 V1 primary Android mobile endpoint delivery contracts. No real FCM."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from backend.app import models
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i10.primary_mobile_endpoint import (
    MULTIPLE_ACTIVE_PRIMARY_ENDPOINTS,
    NO_ACTIVE_PRIMARY_ENDPOINT,
)
from backend.app.services.notifications.delivery_service import (
    FCMAdapter,
    _get_fcm_tokens_for_user,
    provider_delivery_enabled,
)
from backend.tests.test_push_device_install_upsert_v1 import _auth, _register, _tok, _user

_GATE = "SEDI_NOTIFICATION_PROVIDER_DELIVERY_ENABLED"


def _decision(db, user: models.User) -> models.I10NotificationDecision:
    row = models.I10NotificationDecision(
        candidate_key=f"pm-{uuid4().hex[:10]}",
        recipient_user_id=user.id,
        source_owner="I10_TEST",
        source_type="primary_mobile",
        source_id="1",
        semantic_family=I10SemanticFamily.ENGAGEMENT_NUDGE.value,
        decision="SEND",
        reason_code="POLICY_ALLOW",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _queued(db, user: models.User, decision: models.I10NotificationDecision) -> models.Notification:
    notif = models.Notification(
        user_id=user.id,
        type="connection_ping",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=False,
        status="queued",
        sent_at=None,
        ttl_seconds=3600,
        semantic_family=decision.semantic_family,
        i10_policy_decision_id=decision.id,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    decision.notification_id = notif.id
    db.add(decision)
    db.commit()
    return notif


def _seed_active(db, user: models.User, token: str, device_id: str | None = None) -> models.PushDevice:
    row = models.PushDevice(
        user_id=user.id,
        platform="android",
        fcm_token=token,
        device_id=device_id,
        is_active=True,
        last_seen_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _send(db, notif, monkeypatch, fake_send):
    monkeypatch.setenv(_GATE, "true")
    adapter = FCMAdapter(db=db, timeout_sec=1)
    with patch(
        "backend.app.services.notifications.fcm_client.send_push_to_tokens",
        side_effect=fake_send,
    ):
        return adapter.send(notif)


def test_multiple_legacy_actives_fail_closed_no_fcm(db, monkeypatch):
    user = _user(db, "MultiActiveSend")
    _seed_active(db, user, _tok(21), "legacy-a")
    _seed_active(db, user, _tok(22), "legacy-b")
    decision = _decision(db, user)
    notif = _queued(db, user, decision)
    captured = []

    def _fake(**kwargs):
        captured.append(kwargs)
        return (1, [(kwargs["tokens"][0], "mock", None)])

    ok = _send(db, notif, monkeypatch, _fake)
    assert ok is False
    assert captured == []
    assert notif.is_sent is False
    assert notif.status == "failed"
    assert notif.last_error == MULTIPLE_ACTIVE_PRIMARY_ENDPOINTS
    assert _get_fcm_tokens_for_user(db, user.id) == []


def test_exactly_one_active_reaches_send_layer(db, monkeypatch):
    user = _user(db, "OneActiveSend")
    device = _seed_active(db, user, _tok(23), "only-one")
    decision = _decision(db, user)
    notif = _queued(db, user, decision)
    captured = []

    def _fake(**kwargs):
        captured.append(kwargs)
        return (1, [(kwargs["tokens"][0], "mid-1", None)])

    ok = _send(db, notif, monkeypatch, _fake)
    assert ok is True
    assert len(captured) == 1
    assert captured[0]["tokens"] == [device.fcm_token]
    assert notif.is_sent is True
    assert _get_fcm_tokens_for_user(db, user.id) == [device.fcm_token]


def test_zero_active_no_fcm_attempt(db, monkeypatch):
    user = _user(db, "ZeroActiveSend")
    decision = _decision(db, user)
    notif = _queued(db, user, decision)
    captured = []

    def _fake(**kwargs):
        captured.append(kwargs)
        return (1, [(kwargs["tokens"][0], "mock", None)])

    ok = _send(db, notif, monkeypatch, _fake)
    assert ok is False
    assert captured == []
    assert notif.is_sent is False
    assert notif.status == "failed"
    assert notif.last_error == NO_ACTIVE_PRIMARY_ENDPOINT
    assert _get_fcm_tokens_for_user(db, user.id) == []


def test_invalid_fcm_token_deactivates_device(db, monkeypatch):
    user = _user(db, "InvalidTokenRetire")
    device = _seed_active(db, user, _tok(24), "retire-me")
    decision = _decision(db, user)
    notif = _queued(db, user, decision)
    err_body = (
        '{"error":{"status":"NOT_FOUND","message":"Requested entity was not found.",'
        '"details":[{"errorCode":"UNREGISTERED"}]}}'
    )

    def _fake(**kwargs):
        return (0, [(device.fcm_token, None, err_body)])

    ok = _send(db, notif, monkeypatch, _fake)
    assert ok is False
    db.expire_all()
    after = db.query(models.PushDevice).filter(models.PushDevice.id == device.id).one()
    assert after.is_active is False
    assert notif.is_sent is False


def test_provider_off_register_reconciles_but_does_not_send(client, db, monkeypatch):
    monkeypatch.delenv(_GATE, raising=False)
    assert provider_delivery_enabled() is False
    user = _user(db, "ProviderOffReg")
    first = _register(client, user.id, _tok(25), "install-one")
    second = _register(client, user.id, _tok(26), "install-two")
    assert first.status_code == 200 and second.status_code == 200
    db.expire_all()
    rows = db.query(models.PushDevice).filter(models.PushDevice.user_id == user.id).all()
    assert len(rows) == 2
    assert sum(1 for row in rows if row.is_active) == 1
    decision = _decision(db, user)
    notif = _queued(db, user, decision)
    captured = []

    def _fake(**kwargs):
        captured.append(kwargs)
        return (1, [(kwargs["tokens"][0], "mock", None)])

    adapter = FCMAdapter(db=db, timeout_sec=1)
    with patch(
        "backend.app.services.notifications.fcm_client.send_push_to_tokens",
        side_effect=_fake,
    ):
        ok = adapter.send(notif)
    assert ok is False
    assert captured == []
    assert notif.is_sent is False
    assert "PROVIDER_DELIVERY_DISABLED" in (notif.last_error or "")


def test_registration_does_not_change_user_identity(client, db):
    user = _user(db, "IdentityStay")
    before = {
        "id": user.id,
        "name": user.name,
        "secret_key": user.secret_key,
        "preferred_language": user.preferred_language,
        "phone": user.phone,
        "account_type": user.account_type,
    }
    r = client.post(
        "/notifications/push/register",
        headers=_auth(user.id),
        json={
            "user_id": user.id,
            "platform": "android",
            "fcm_token": _tok(27),
            "device_id": "install-identity",
        },
    )
    assert r.status_code == 200
    db.expire_all()
    after = db.query(models.User).filter(models.User.id == before["id"]).one()
    assert after.id == before["id"]
    assert after.name == before["name"]
    assert after.secret_key == before["secret_key"]
    assert after.preferred_language == before["preferred_language"]
    assert after.phone == before["phone"]
    assert after.account_type == before["account_type"]


def _admin_send_now(client, user_id: int, monkeypatch, *, provider_on: bool):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-primary-mobile")
    if provider_on:
        monkeypatch.setenv(_GATE, "true")
    else:
        monkeypatch.delenv(_GATE, raising=False)
    captured = []

    def _fake(**kwargs):
        captured.append(kwargs)
        return (1, [(kwargs["tokens"][0], "mock", None)])

    with patch(
        "backend.app.services.notifications.fcm_client.send_push_to_tokens",
        side_effect=_fake,
    ):
        response = client.post(
            f"/notifications/admin/notif/send_now?user_id={user_id}&channel=engagement&force=true",
            headers={"X-Admin-Token": "admin-primary-mobile"},
        )
    return response, captured


def test_admin_send_now_zero_active_explicit_reason(client, db, monkeypatch):
    user = _user(db, "AdminZeroActive")
    r, captured = _admin_send_now(client, user.id, monkeypatch, provider_on=True)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["attempted_tokens"] == 0
    assert body["sent_success"] == 0
    assert body["reasons"] == [NO_ACTIVE_PRIMARY_ENDPOINT]
    assert captured == []


def test_admin_send_now_multiple_active_explicit_reason(client, db, monkeypatch):
    user = _user(db, "AdminMultiActive")
    _seed_active(db, user, _tok(31), "admin-a")
    _seed_active(db, user, _tok(32), "admin-b")
    r, captured = _admin_send_now(client, user.id, monkeypatch, provider_on=True)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["attempted_tokens"] == 0
    assert body["sent_success"] == 0
    assert body["reasons"] == [MULTIPLE_ACTIVE_PRIMARY_ENDPOINTS]
    assert captured == []


def test_admin_send_now_one_active_selects_exact_token(client, db, monkeypatch):
    user = _user(db, "AdminOneActive")
    device = _seed_active(db, user, _tok(33), "admin-only")
    r, captured = _admin_send_now(client, user.id, monkeypatch, provider_on=True)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["attempted_tokens"] == 1
    assert _get_fcm_tokens_for_user(db, user.id) == [device.fcm_token]
    assert captured == []
    assert "I10_PROVIDER_AUTHORITY_REQUIRED" in body["reasons"]


def test_admin_send_now_provider_off_blocks_before_endpoint_send(client, db, monkeypatch):
    user = _user(db, "AdminProviderOff")
    _seed_active(db, user, _tok(34), "admin-off")
    r, captured = _admin_send_now(client, user.id, monkeypatch, provider_on=False)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["blocked"] is True
    assert body["attempted_tokens"] == 0
    assert "PROVIDER_DELIVERY_DISABLED" in body["reasons"]
    assert captured == []
    assert provider_delivery_enabled() is False
