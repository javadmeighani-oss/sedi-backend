"""Device-token auth for firmware-facing /device/* operational routes (Phase 1D-b)."""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.core.security import create_access_token
from backend.app.models import Device, Notification, User


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _device_header(device_token: str) -> dict[str, str]:
    return {"X-DEVICE-TOKEN": device_token}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _register_device(client, db, user: User, device_id: str) -> str:
    response = client.post(
        "/devices/register",
        json={"device_id": device_id, "device_type": "heart_rate"},
        headers=_auth_header(user.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    token = data.get("data", {}).get("token")
    assert isinstance(token, str) and token
    return token


@pytest.fixture(autouse=True)
def _db_only_auth_mode(monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "db_only")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)


def test_pending_commands_requires_device_token(client, db):
    u = _create_user(db, "PendingNoToken")
    token = _register_device(client, db, u, "PendingDev001")
    response = client.get(f"/device/pending-commands?device_id=PendingDev001")
    assert response.status_code == 422


def test_pending_commands_works_for_device_owner(client, db):
    u = _create_user(db, "PendingOwner")
    device_id = "PendingDevOwner001"
    device_token = _register_device(client, db, u, device_id)

    db.add(
        Notification(
            user_id=u.id,
            type="health_alert",
            title="Alert",
            body="High heart rate",
            priority="high",
            is_read=False,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.get(
        f"/device/pending-commands?device_id={device_id}",
        headers=_device_header(device_token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    commands = (payload.get("data") or {}).get("commands") or []
    assert len(commands) >= 1


def test_pending_commands_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "PendingLegacy")
    device_id = "PendingDevLegacy001"
    device_token = _register_device(client, db, u, device_id)

    response = client.get(
        f"/device/pending-commands?device_id={device_id}&user_id={u.id}",
        headers=_device_header(device_token),
    )
    assert response.status_code == 422


def test_heartbeat_requires_device_token(client, db):
    u = _create_user(db, "HeartNoToken")
    _register_device(client, db, u, "HeartDev001")
    response = client.post(
        "/device/heartbeat",
        json={"device_id": "HeartDev001", "status": "active"},
    )
    assert response.status_code == 422


def test_heartbeat_works_with_valid_device_token(client, db):
    u = _create_user(db, "HeartOwner")
    device_id = "HeartDevOwner001"
    device_token = _register_device(client, db, u, device_id)

    response = client.post(
        "/device/heartbeat",
        json={"device_id": device_id, "status": "active", "battery": 90},
        headers=_device_header(device_token),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True

    dev = db.query(Device).filter(Device.device_id == device_id).first()
    assert dev is not None
    assert dev.last_seen_at is not None


def test_heartbeat_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "HeartLegacy")
    device_id = "HeartDevLegacy001"
    device_token = _register_device(client, db, u, device_id)

    response = client.post(
        "/device/heartbeat",
        json={"device_id": device_id, "user_id": u.id, "status": "active"},
        headers=_device_header(device_token),
    )
    assert response.status_code == 422


def test_acknowledge_requires_device_token(client, db):
    u = _create_user(db, "AckNoToken")
    _register_device(client, db, u, "AckDev001")
    response = client.post(
        "/device/acknowledge",
        json={"device_id": "AckDev001", "sound_id": "alert_default", "status": "played"},
    )
    assert response.status_code == 422


def test_acknowledge_works_with_valid_device_token(client, db):
    u = _create_user(db, "AckOwner")
    device_id = "AckDevOwner001"
    device_token = _register_device(client, db, u, device_id)

    response = client.post(
        "/device/acknowledge",
        json={"device_id": device_id, "sound_id": "alert_default", "status": "played"},
        headers=_device_header(device_token),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True


def test_acknowledge_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "AckLegacy")
    device_id = "AckDevLegacy001"
    device_token = _register_device(client, db, u, device_id)

    response = client.post(
        "/device/acknowledge",
        json={"device_id": device_id, "user_id": u.id, "sound_id": "x", "status": "played"},
        headers=_device_header(device_token),
    )
    assert response.status_code == 422


def test_ingest_happy_path_still_works(client, db):
    u = _create_user(db, "IngestHappy")
    device_id = "IngestHappy001"
    device_token = _register_device(client, db, u, device_id)

    response = client.post(
        "/device/ingest",
        headers=_device_header(device_token),
        json={
            "user_id": u.id,
            "device_id": device_id,
            "event_type": "heart_rate",
            "payload": {"bpm": 82},
        },
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True


def test_ingest_ignores_mobile_user_id_for_subject_attribution(client, db):
    """I9: device token + binding are authoritative; mobile user_id is not data owner."""
    from backend.app.models import PhysiologicalMeasurement

    u = _create_user(db, "IngestOwner")
    other = _create_user(db, "IngestOther")
    device_id = "IngestMismatch001"
    device_token = _register_device(client, db, u, device_id)
    device = db.query(Device).filter(Device.device_id == device_id).first()

    response = client.post(
        "/device/ingest",
        headers=_device_header(device_token),
        json={
            "user_id": other.id,
            "device_id": device_id,
            "event_type": "heart_rate",
            "payload": {"bpm": 82},
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    pm = db.query(PhysiologicalMeasurement).order_by(PhysiologicalMeasurement.id.desc()).first()
    assert pm is not None
    assert pm.health_subject_id == device.health_subject_id
    assert pm.user_id == u.id


def test_pending_commands_cross_user_isolation(client, db):
    user_a = _create_user(db, "PendingUserA")
    user_b = _create_user(db, "PendingUserB")
    device_a = "PendingCrossA001"
    token_a = _register_device(client, db, user_a, device_a)

    db.add(
        Notification(
            user_id=user_b.id,
            type="health_alert",
            title="B alert",
            body="User B only",
            priority="critical",
            is_read=False,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.get(
        f"/device/pending-commands?device_id={device_a}",
        headers=_device_header(token_a),
    )
    assert response.status_code == 200
    commands = (response.json().get("data") or {}).get("commands") or []
    assert all("User B only" not in (c.get("text") or "") for c in commands)


def test_heartbeat_cross_user_isolation(client, db):
    user_a = _create_user(db, "HeartUserA")
    user_b = _create_user(db, "HeartUserB")
    device_b = "HeartCrossB001"
    token_b = _register_device(client, db, user_b, device_b)

    response = client.post(
        "/device/heartbeat",
        json={"device_id": device_b, "status": "active"},
        headers=_device_header(token_b),
    )
    assert response.status_code == 200

    dev = db.query(Device).filter(Device.device_id == device_b).first()
    assert dev.user_id == user_b.id

    response_bad = client.post(
        "/device/heartbeat",
        json={"device_id": device_b, "status": "active"},
        headers=_device_header("invalid-token-value"),
    )
    assert response_bad.status_code == 401


def test_acknowledge_cross_user_isolation(client, db):
    user_a = _create_user(db, "AckUserA")
    user_b = _create_user(db, "AckUserB")
    device_b = "AckCrossB001"
    token_b = _register_device(client, db, user_b, device_b)

    before = db.query(Notification).filter(Notification.user_id == user_a.id).count()

    response = client.post(
        "/device/acknowledge",
        json={"device_id": device_b, "sound_id": "alert_default", "status": "played"},
        headers=_device_header(token_b),
    )
    assert response.status_code == 200

    after_a = db.query(Notification).filter(Notification.user_id == user_a.id).count()
    after_b = db.query(Notification).filter(Notification.user_id == user_b.id).count()
    assert after_a == before
    assert after_b == before + 1
