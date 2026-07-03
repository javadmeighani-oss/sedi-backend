"""Gate 5-A — Gadget Hub + sensor registry + status foundation tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.core.device_auth import hash_device_token
from backend.app.core.security import create_access_token
from backend.app.models import Device, DeviceSensor, User
from backend.app.services.gate5.gadget_hub_status import GADGET_HUB_DEVICE_TYPE


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user(db):
    u = User(name="Hub Owner", secret_key="pw", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def other_user(db):
    u = User(name="Other User", secret_key="pw2", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _register_hub(client: TestClient, user_id: int, device_id: str = "hub-001") -> dict:
    r = client.post(
        "/devices/register",
        json={"device_id": device_id, "device_type": GADGET_HUB_DEVICE_TYPE},
        headers=_auth_header(user_id),
    )
    assert r.status_code == 200
    return r.json()["data"]


def test_register_gadget_hub_success(client: TestClient, user):
    data = _register_hub(client, user.id)
    assert data["device_id"] == "hub-001"
    assert isinstance(data["token"], str) and len(data["token"]) >= 32


def test_second_active_gadget_hub_returns_409(client: TestClient, user):
    _register_hub(client, user.id, "hub-a")
    r = client.post(
        "/devices/register",
        json={"device_id": "hub-b", "device_type": GADGET_HUB_DEVICE_TYPE},
        headers=_auth_header(user.id),
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "GADGET_HUB_ALREADY_REGISTERED"


def test_legacy_non_hub_device_registration_still_works(client: TestClient, user):
    r1 = client.post(
        "/devices/register",
        json={"device_id": "Sedi-HR-1", "device_type": "heart_rate"},
        headers=_auth_header(user.id),
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/devices/register",
        json={"device_id": "Sedi-HR-2", "device_type": "heart_rate"},
        headers=_auth_header(user.id),
    )
    assert r2.status_code == 200


def test_heartbeat_persists_battery_and_firmware(client: TestClient, db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id)
    token = reg["token"]

    r = client.post(
        "/device/heartbeat",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-001",
            "battery_level": 87,
            "firmware_version": "1.0.0",
            "hardware_version": "hub-dev-1",
            "hub_status": "online",
        },
    )
    assert r.status_code == 200

    dev = db.query(Device).filter(Device.device_id == "hub-001").first()
    assert dev.battery_level == 87.0
    assert dev.firmware_version == "1.0.0"
    assert dev.hardware_version == "hub-dev-1"
    assert dev.last_heartbeat_at is not None


def test_heartbeat_legacy_battery_field(client: TestClient, db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id, "hub-battery-legacy")
    token = reg["token"]

    client.post(
        "/device/heartbeat",
        headers={"X-DEVICE-TOKEN": token},
        json={"device_id": "hub-battery-legacy", "battery": 55},
    )
    dev = db.query(Device).filter(Device.device_id == "hub-battery-legacy").first()
    assert dev.battery_level == 55.0


def test_hub_status_before_registration(client: TestClient, user):
    r = client.get("/devices/hub-status", headers=_auth_header(user.id))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["has_hub"] is False
    assert data["status"] == "not_registered"
    assert data["hub"] is None
    assert data["sensors"] == []


def test_hub_status_after_registration(client: TestClient, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id, "hub-status-1")
    token = reg["token"]

    client.post(
        "/device/heartbeat",
        headers={"X-DEVICE-TOKEN": token},
        json={"device_id": "hub-status-1", "battery_level": 90, "firmware_version": "1.0.0"},
    )

    r = client.get("/devices/hub-status", headers=_auth_header(user.id))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["has_hub"] is True
    assert data["status"] == "connected"
    hub = data["hub"]
    assert hub["device_id"] == "hub-status-1"
    assert hub["device_type"] == GADGET_HUB_DEVICE_TYPE
    assert hub["battery_level"] == 90
    assert "token" not in hub
    assert "token_hash" not in hub


def test_hub_status_auth_isolation(client: TestClient, user, other_user):
    _register_hub(client, user.id, "hub-isolated")
    r = client.get("/devices/hub-status", headers=_auth_header(other_user.id))
    assert r.status_code == 200
    assert r.json()["data"]["has_hub"] is False


def test_gadget_hub_sensor_sync_and_status(client: TestClient, db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id, "hub-sync")
    token = reg["token"]

    sync_body = {
        "device_id": "hub-sync",
        "sensors": [
            {
                "sensor_key": "chest-ecg-001",
                "sensor_type": "ecg",
                "display_name": "Chest ECG Sensor",
                "connection_status": "connected",
                "battery_level": 91,
                "firmware_version": "0.1.0",
                "hardware_version": "ecg-dev-1",
                "capabilities": {
                    "signals": ["ecg", "heart_rate"],
                    "placement": "chest",
                    "connection": "bluetooth",
                },
                "last_signal_at": "2026-07-03T08:00:00Z",
            }
        ],
    }
    r = client.post("/device/sensors/sync", headers={"X-DEVICE-TOKEN": token}, json=sync_body)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["data"]["synced_count"] == 1

    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    assert sensor is not None
    caps = json.loads(sensor.capabilities_json)
    assert caps["signals"] == ["ecg", "heart_rate"]

    status = client.get("/devices/hub-status", headers=_auth_header(user.id)).json()["data"]
    assert len(status["sensors"]) == 1
    assert status["sensors"][0]["sensor_key"] == "chest-ecg-001"
    assert status["sensors"][0]["capabilities"]["placement"] == "chest"


def test_sensor_sync_upserts_by_sensor_key(client: TestClient, db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id, "hub-upsert")
    token = reg["token"]
    base = {"device_id": "hub-upsert", "sensors": [{"sensor_key": "s1", "sensor_type": "ecg", "connection_status": "connected"}]}

    client.post("/device/sensors/sync", headers={"X-DEVICE-TOKEN": token}, json=base)
    client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-upsert",
            "sensors": [{"sensor_key": "s1", "sensor_type": "ecg", "connection_status": "recently_seen", "battery_level": 80}],
        },
    )
    rows = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "s1").all()
    assert len(rows) == 1
    assert rows[0].connection_status == "recently_seen"
    assert rows[0].battery_level == 80


def test_non_hub_device_cannot_sync_sensors(client: TestClient, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    r = client.post(
        "/devices/register",
        json={"device_id": "hr-only", "device_type": "heart_rate"},
        headers=_auth_header(user.id),
    )
    token = r.json()["data"]["token"]
    sync = client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hr-only",
            "sensors": [{"sensor_key": "x", "sensor_type": "ecg", "connection_status": "connected"}],
        },
    )
    assert sync.status_code == 403


def test_revoked_hub_status(client: TestClient, user):
    _register_hub(client, user.id, "hub-revoked")
    client.post("/devices/hub-revoked/revoke", headers=_auth_header(user.id))
    data = client.get("/devices/hub-status", headers=_auth_header(user.id)).json()["data"]
    assert data["has_hub"] is True
    assert data["status"] == "revoked"


def test_hub_status_disconnected_when_stale(client: TestClient, db, user):
    _register_hub(client, user.id, "hub-stale")
    dev = db.query(Device).filter(Device.device_id == "hub-stale").first()
    dev.last_heartbeat_at = datetime.utcnow() - timedelta(hours=2)
    dev.last_seen_at = dev.last_heartbeat_at
    db.add(dev)
    db.commit()

    data = client.get("/devices/hub-status", headers=_auth_header(user.id)).json()["data"]
    assert data["status"] == "disconnected"
