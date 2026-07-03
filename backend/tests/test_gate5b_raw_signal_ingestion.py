"""Gate 5-B — Raw heart/ECG store-only ingestion tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.models import Device, DeviceEvent, DeviceSensor, Notification, RawSignalBatch, User, UserMemoryFact
from backend.app.services.gate5.gadget_hub_status import GADGET_HUB_DEVICE_TYPE


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user(db):
    u = User(name="Raw Signal Owner", secret_key="pw", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _register_hub(client: TestClient, user_id: int, device_id: str = "hub-raw-001") -> dict:
    r = client.post(
        "/devices/register",
        json={"device_id": device_id, "device_type": GADGET_HUB_DEVICE_TYPE},
        headers=_auth_header(user_id),
    )
    assert r.status_code == 200
    return r.json()["data"]


def _sync_ecg_sensor(client: TestClient, token: str, device_id: str, sensor_key: str = "chest-ecg-001") -> None:
    r = client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": device_id,
            "sensors": [
                {
                    "sensor_key": sensor_key,
                    "sensor_type": "ecg",
                    "connection_status": "connected",
                }
            ],
        },
    )
    assert r.status_code == 200


def _raw_batch_body(
    device_id: str = "hub-raw-001",
    sensor_key: str = "chest-ecg-001",
    client_batch_id: str = "batch-001",
    signal_type: str = "ecg",
    sample_count: int = 4,
) -> dict:
    started = datetime(2026, 7, 3, 8, 0, 0)
    ended = started + timedelta(seconds=8)
    return {
        "device_id": device_id,
        "sensor_key": sensor_key,
        "client_batch_id": client_batch_id,
        "signal_type": signal_type,
        "sample_rate_hz": 250.0,
        "started_at": started.isoformat() + "Z",
        "ended_at": ended.isoformat() + "Z",
        "sample_count": sample_count,
        "samples": [1024.0, 1025.0, 1023.0, 1022.0][:sample_count],
        "metadata": {"sample_unit": "adc_counts", "compression": "none"},
        "quality_metadata": {"lead_off": False, "motion_detected": False},
    }


@pytest.fixture
def hub_with_ecg(client: TestClient, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id)
    _sync_ecg_sensor(client, reg["token"], "hub-raw-001")
    return reg


def test_happy_path_raw_signal_ingest(client: TestClient, db, user, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body()

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["ok"] is True
    assert data["data"]["dedupe_hit"] is False
    assert data["data"]["sample_count"] == 4
    assert data["data"]["storage_backend"] == "postgres_json"

    row = db.query(RawSignalBatch).filter(RawSignalBatch.client_batch_id == "batch-001").first()
    assert row is not None
    assert row.signal_type == "ecg"
    assert row.user_id == user.id
    assert len(row.samples_json) == 4


def test_duplicate_replay_returns_200_dedupe_hit(client: TestClient, db, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body(client_batch_id="batch-dup")

    r1 = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r1.status_code == 201

    r2 = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r2.status_code == 200
    assert r2.json()["data"]["dedupe_hit"] is True
    assert r2.json()["data"]["batch_id"] == r1.json()["data"]["batch_id"]

    assert db.query(RawSignalBatch).filter(RawSignalBatch.client_batch_id == "batch-dup").count() == 1


def test_non_hub_device_rejected(client: TestClient, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = client.post(
        "/devices/register",
        json={"device_id": "hr-only", "device_type": "heart_rate"},
        headers=_auth_header(user.id),
    ).json()["data"]

    r = client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": reg["token"]},
        json=_raw_batch_body(device_id="hr-only"),
    )
    assert r.status_code == 403


def test_unknown_sensor_key_rejected(client: TestClient, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body(sensor_key="missing-sensor")

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 403


def test_revoked_sensor_rejected(client: TestClient, db, hub_with_ecg):
    token = hub_with_ecg["token"]
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    sensor.revoked_at = datetime.utcnow()
    db.add(sensor)
    db.commit()

    r = client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(),
    )
    assert r.status_code == 403


def test_missing_device_token_rejected(client: TestClient, hub_with_ecg):
    r = client.post("/device/signals/raw", json=_raw_batch_body())
    assert r.status_code == 422


def test_wrong_token_rejected(client: TestClient, hub_with_ecg):
    r = client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": "not-a-valid-token"},
        json=_raw_batch_body(),
    )
    assert r.status_code in (401, 403)


def test_sample_count_mismatch_returns_422(client: TestClient, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body(sample_count=10)

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 422


def test_started_at_not_before_ended_at_returns_422(client: TestClient, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body()
    body["ended_at"] = body["started_at"]

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 422


def test_invalid_signal_type_returns_422(client: TestClient, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body()
    body["signal_type"] = "blood_pressure"

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 422


def test_signal_type_unknown_accepted(client: TestClient, db, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body(client_batch_id="batch-unknown", signal_type="unknown")

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 201
    row = db.query(RawSignalBatch).filter(RawSignalBatch.client_batch_id == "batch-unknown").first()
    assert row.signal_type == "unknown"


def test_signal_type_ecg_rejects_non_ecg_sensor(client: TestClient, hub_with_ecg):
    token = hub_with_ecg["token"]
    client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-raw-001",
            "sensors": [{"sensor_key": "hr-wrist", "sensor_type": "heart_rate", "connection_status": "connected"}],
        },
    )
    body = _raw_batch_body(sensor_key="hr-wrist", client_batch_id="batch-ecg-mismatch", signal_type="ecg")

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 422


def test_signal_type_heart_rate_raw_accepts_ecg_or_heart_rate_sensor(client: TestClient, db, hub_with_ecg):
    token = hub_with_ecg["token"]

    body_ecg = _raw_batch_body(client_batch_id="batch-hr-raw-ecg", signal_type="heart_rate_raw")
    assert client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body_ecg).status_code == 201

    client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-raw-001",
            "sensors": [{"sensor_key": "hr-band", "sensor_type": "heart_rate", "connection_status": "connected"}],
        },
    )
    body_hr = _raw_batch_body(
        sensor_key="hr-band",
        client_batch_id="batch-hr-raw-hr",
        signal_type="heart_rate_raw",
    )
    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body_hr)
    assert r.status_code == 201
    assert db.query(RawSignalBatch).filter(RawSignalBatch.client_batch_id == "batch-hr-raw-hr").count() == 1


def test_forbidden_clinical_top_level_field_returns_422(client: TestClient, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body()
    body["diagnosis"] = "afib"

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 422


def test_forbidden_clinical_metadata_field_returns_422(client: TestClient, hub_with_ecg):
    token = hub_with_ecg["token"]
    body = _raw_batch_body()
    body["metadata"] = {"arrhythmia": "possible"}

    r = client.post("/device/signals/raw", headers={"X-DEVICE-TOKEN": token}, json=body)
    assert r.status_code == 422


def test_sensor_last_signal_at_updated(client: TestClient, db, hub_with_ecg):
    token = hub_with_ecg["token"]
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    assert sensor.last_signal_at is None

    client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(client_batch_id="batch-last-signal"),
    )

    db.refresh(sensor)
    assert sensor.last_signal_at is not None


def test_hub_last_seen_at_updated(client: TestClient, db, hub_with_ecg):
    token = hub_with_ecg["token"]
    hub = db.query(Device).filter(Device.device_id == "hub-raw-001").first()
    hub.last_seen_at = datetime.utcnow() - timedelta(hours=2)
    db.add(hub)
    db.commit()
    before = hub.last_seen_at

    client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(client_batch_id="batch-hub-seen"),
    )

    db.refresh(hub)
    assert hub.last_seen_at > before


def test_no_notification_rows_created(client: TestClient, db, user, hub_with_ecg):
    token = hub_with_ecg["token"]
    before = db.query(Notification).filter(Notification.user_id == user.id).count()

    client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(client_batch_id="batch-no-notif"),
    )

    after = db.query(Notification).filter(Notification.user_id == user.id).count()
    assert after == before


def test_no_device_event_rows_created(client: TestClient, db, user, hub_with_ecg):
    token = hub_with_ecg["token"]
    before = db.query(DeviceEvent).filter(DeviceEvent.user_id == user.id).count()

    client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(client_batch_id="batch-no-event"),
    )

    after = db.query(DeviceEvent).filter(DeviceEvent.user_id == user.id).count()
    assert after == before


def test_no_user_memory_facts_created(client: TestClient, db, user, hub_with_ecg):
    token = hub_with_ecg["token"]
    before = db.query(UserMemoryFact).filter(UserMemoryFact.user_id == user.id).count()

    client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(client_batch_id="batch-no-memory"),
    )

    after = db.query(UserMemoryFact).filter(UserMemoryFact.user_id == user.id).count()
    assert after == before
