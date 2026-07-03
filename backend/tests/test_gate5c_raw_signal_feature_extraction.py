"""Gate 5-C — Raw signal batch technical feature extraction tests."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.models import (
    Device,
    DeviceEvent,
    DeviceSensor,
    Notification,
    RawSignalBatch,
    RawSignalBatchFeature,
    User,
    UserMemoryFact,
)
from backend.app.services.gate5.gadget_hub_status import GADGET_HUB_DEVICE_TYPE
from backend.app.services.gate5.raw_signal_feature_compute import (
    FORBIDDEN_OUTPUT_KEYS,
    compute_raw_signal_features,
)
from backend.app.services.gate5.raw_signal_feature_extraction import (
    RawSignalFeatureExtractionError,
    process_pending_raw_signal_batches,
    process_raw_signal_batch,
)
from backend.app.services.gate5.raw_signal_ingestion import build_raw_signal_dedupe_key

_TEST_ADMIN_TOKEN = "test-gate5c-admin"


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-ADMIN-TOKEN": token}


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)


@pytest.fixture
def user(db):
    u = User(name="Feature Owner", secret_key="pw", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _register_hub(client: TestClient, user_id: int, device_id: str = "hub-feat-001") -> dict:
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
            "sensors": [{"sensor_key": sensor_key, "sensor_type": "ecg", "connection_status": "connected"}],
        },
    )
    assert r.status_code == 200


def _raw_batch_body(
    client_batch_id: str = "batch-feat-001",
    sample_count: int = 4,
    duration_seconds: float = 8.0,
) -> dict:
    started = datetime(2026, 7, 3, 8, 0, 0)
    ended = started + timedelta(seconds=duration_seconds)
    samples = [1024.0, 1025.0, 1023.0, 1022.0][:sample_count]
    return {
        "device_id": "hub-feat-001",
        "sensor_key": "chest-ecg-001",
        "client_batch_id": client_batch_id,
        "signal_type": "ecg",
        "sample_rate_hz": 250.0,
        "started_at": started.isoformat() + "Z",
        "ended_at": ended.isoformat() + "Z",
        "sample_count": sample_count,
        "samples": samples,
        "metadata": {"sample_unit": "adc_counts", "compression": "none"},
        "quality_metadata": {"lead_off": False, "motion_detected": False},
    }


@pytest.fixture
def hub_with_ecg(client: TestClient, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id)
    _sync_ecg_sensor(client, reg["token"], "hub-feat-001")
    return reg


def _ingest_batch(client: TestClient, token: str, client_batch_id: str = "batch-feat-001") -> int:
    r = client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(client_batch_id=client_batch_id),
    )
    assert r.status_code == 201
    return r.json()["data"]["batch_id"]


def _insert_batch_row(
    db,
    *,
    user_id: int,
    hub: Device,
    sensor: DeviceSensor,
    client_batch_id: str,
    samples,
    sample_count: int | None = None,
    storage_backend: str = "postgres_json",
    duration_seconds: float = 8.0,
) -> RawSignalBatch:
    started = datetime(2026, 7, 3, 8, 0, 0)
    ended = started + timedelta(seconds=duration_seconds)
    now = datetime.utcnow()
    declared_count = sample_count if sample_count is not None else len(samples)
    batch = RawSignalBatch(
        user_id=user_id,
        hub_device_id=hub.id,
        hub_device_id_str=hub.device_id,
        sensor_id=sensor.id,
        sensor_key=sensor.sensor_key,
        signal_type="ecg",
        sample_rate_hz=250.0,
        started_at=started,
        ended_at=ended,
        sample_count=declared_count,
        samples_json=samples,
        metadata_json={"sample_unit": "adc_counts"},
        quality_metadata_json={"lead_off": False},
        client_batch_id=client_batch_id,
        dedupe_key=build_raw_signal_dedupe_key(hub.id, sensor.sensor_key, client_batch_id),
        received_at=now,
        created_at=now,
        storage_backend=storage_backend,
        object_storage_key=None,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def test_happy_path_process_known_samples(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"])
    result = process_raw_signal_batch(db, batch_id)
    assert result.processing_status == "completed"
    assert result.skipped is False

    row = db.query(RawSignalBatchFeature).filter(RawSignalBatchFeature.id == result.feature_id).first()
    assert row is not None
    assert row.features_json is not None
    assert row.quality_json is not None


def test_computed_min_max_mean_std(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-stats")
    result = process_raw_signal_batch(db, batch_id)
    features = db.query(RawSignalBatchFeature).get(result.feature_id).features_json

    assert features["min_value"] == 1022.0
    assert features["max_value"] == 1025.0
    assert features["mean_value"] == 1023.5
    assert features["std_dev"] == pytest.approx(math.sqrt(1.25), rel=1e-6)


def test_duration_and_effective_sample_rate(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-duration")
    features = db.query(RawSignalBatchFeature).get(
        process_raw_signal_batch(db, batch_id).feature_id
    ).features_json

    assert features["duration_seconds"] == 8.0
    assert features["effective_sample_rate_hz"] == pytest.approx(0.5, rel=1e-6)
    assert features["expected_sample_count"] == 2000


def test_idempotent_same_version_returns_same_row(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-idem")
    first = process_raw_signal_batch(db, batch_id)
    second = process_raw_signal_batch(db, batch_id)

    assert second.skipped is True
    assert second.feature_id == first.feature_id
    assert db.query(RawSignalBatchFeature).filter(RawSignalBatchFeature.raw_signal_batch_id == batch_id).count() == 1


def test_new_processing_version_creates_second_row(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-ver")
    process_raw_signal_batch(db, batch_id, processing_version="gate5c_v1")
    process_raw_signal_batch(db, batch_id, processing_version="gate5c_v2")

    rows = (
        db.query(RawSignalBatchFeature)
        .filter(RawSignalBatchFeature.raw_signal_batch_id == batch_id)
        .order_by(RawSignalBatchFeature.id.asc())
        .all()
    )
    assert len(rows) == 2
    assert {r.processing_version for r in rows} == {"gate5c_v1", "gate5c_v2"}


def test_sample_count_mismatch_sets_quality_flag(client: TestClient, db, user, hub_with_ecg):
    hub = db.query(Device).filter(Device.device_id == "hub-feat-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-mismatch",
        samples=[1.0, 2.0, 3.0, 4.0],
        sample_count=10,
    )
    result = process_raw_signal_batch(db, batch.id)
    quality = db.query(RawSignalBatchFeature).get(result.feature_id).quality_json
    features = db.query(RawSignalBatchFeature).get(result.feature_id).features_json

    assert features["sample_count_mismatch"] is True
    assert "sample_count_mismatch" in quality["quality_flags"]


def test_short_window_sets_quality_flag(client: TestClient, db, user, hub_with_ecg):
    hub = db.query(Device).filter(Device.device_id == "hub-feat-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-short",
        samples=[1.0, 2.0],
        duration_seconds=0.5,
    )
    quality = db.query(RawSignalBatchFeature).get(process_raw_signal_batch(db, batch.id).feature_id).quality_json
    assert "short_window" in quality["quality_flags"]


def test_object_storage_backend_fails(client: TestClient, db, user, hub_with_ecg):
    hub = db.query(Device).filter(Device.device_id == "hub-feat-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-s3",
        samples=[1.0, 2.0, 3.0],
        storage_backend="object_storage",
    )
    result = process_raw_signal_batch(db, batch.id)
    row = db.query(RawSignalBatchFeature).get(result.feature_id)

    assert result.processing_status == "failed"
    assert row.error_code == "OBJECT_STORAGE_NOT_SUPPORTED"


def test_invalid_samples_handled_safely(client: TestClient, db, user, hub_with_ecg):
    hub = db.query(Device).filter(Device.device_id == "hub-feat-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-invalid",
        samples=[1.0, float("nan"), 3.0],
    )
    result = process_raw_signal_batch(db, batch.id)
    row = db.query(RawSignalBatchFeature).get(result.feature_id)

    assert result.processing_status == "completed"
    assert row.features_json["invalid_sample_ratio"] > 0
    assert "high_invalid_sample_ratio" in row.quality_json["quality_flags"]


def test_missing_batch_returns_controlled_error(db):
    with pytest.raises(RawSignalFeatureExtractionError) as exc:
        process_raw_signal_batch(db, 999999)
    assert exc.value.code == "BATCH_NOT_FOUND"


def test_process_pending_respects_limit(client: TestClient, db, user, hub_with_ecg):
    hub = db.query(Device).filter(Device.device_id == "hub-feat-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    for i in range(3):
        _insert_batch_row(
            db,
            user_id=user.id,
            hub=hub,
            sensor=sensor,
            client_batch_id=f"batch-pending-{i}",
            samples=[1.0, 2.0, 3.0, 4.0],
        )

    summary = process_pending_raw_signal_batches(db, limit=2)
    assert summary.processed == 2
    assert summary.completed == 2


def test_process_pending_skips_already_completed(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-done")
    process_raw_signal_batch(db, batch_id)

    summary = process_pending_raw_signal_batches(db, limit=10)
    assert summary.processed == 0


def test_process_pending_skips_already_failed(client: TestClient, db, user, hub_with_ecg):
    hub = db.query(Device).filter(Device.device_id == "hub-feat-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-pending-failed",
        samples=[1.0, 2.0, 3.0],
        storage_backend="object_storage",
    )
    process_raw_signal_batch(db, batch.id)

    summary = process_pending_raw_signal_batches(db, limit=10)
    assert summary.processed == 0


def test_process_pending_returns_summary_counts(client: TestClient, db, user, hub_with_ecg):
    hub = db.query(Device).filter(Device.device_id == "hub-feat-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-001").first()
    _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-summary-ok",
        samples=[10.0, 11.0, 12.0],
    )
    _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-summary-fail",
        samples=[1.0],
        storage_backend="object_storage",
    )

    summary = process_pending_raw_signal_batches(db, limit=10)
    assert summary.processing_version == "gate5c_v1"
    assert summary.processed == 2
    assert summary.completed == 1
    assert summary.failed == 1


def test_no_notification_rows_created(client: TestClient, db, user, hub_with_ecg):
    before = db.query(Notification).filter(Notification.user_id == user.id).count()
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-no-notif")
    process_raw_signal_batch(db, batch_id)
    after = db.query(Notification).filter(Notification.user_id == user.id).count()
    assert after == before


def test_no_device_event_rows_created(client: TestClient, db, user, hub_with_ecg):
    before = db.query(DeviceEvent).filter(DeviceEvent.user_id == user.id).count()
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-no-event")
    process_raw_signal_batch(db, batch_id)
    after = db.query(DeviceEvent).filter(DeviceEvent.user_id == user.id).count()
    assert after == before


def test_no_user_memory_facts_created(client: TestClient, db, user, hub_with_ecg):
    before = db.query(UserMemoryFact).filter(UserMemoryFact.user_id == user.id).count()
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-no-memory")
    process_raw_signal_batch(db, batch_id)
    after = db.query(UserMemoryFact).filter(UserMemoryFact.user_id == user.id).count()
    assert after == before


def test_forbidden_clinical_output_keys_not_emitted(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-safe-keys")
    row = db.query(RawSignalBatchFeature).get(process_raw_signal_batch(db, batch_id).feature_id)

    for payload in (row.features_json, row.quality_json):
        for key in payload:
            assert str(key).lower() not in FORBIDDEN_OUTPUT_KEYS

    computed = compute_raw_signal_features(
        samples=[1.0, 2.0, 3.0],
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        ended_at=datetime(2026, 1, 1, 0, 0, 2),
        declared_sample_rate_hz=10.0,
        declared_sample_count=3,
    )
    for payload in (computed.features, computed.quality):
        for key in payload:
            assert str(key).lower() not in FORBIDDEN_OUTPUT_KEYS


def test_ops_endpoint_rejects_without_admin_token(client: TestClient, admin_env, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-ops-auth")
    r = client.post(f"/ops/raw-signals/process/{batch_id}", json={})
    assert r.status_code == 403


def test_ops_endpoint_fails_closed_if_admin_token_unset(client: TestClient, monkeypatch, hub_with_ecg):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    r = client.post("/ops/raw-signals/process-pending", json={"limit": 1}, headers=_admin_header())
    assert r.status_code == 403
    assert r.json()["detail"] == "admin_disabled"


def test_ops_process_pending_happy_path(client: TestClient, admin_env, hub_with_ecg):
    _ingest_batch(client, hub_with_ecg["token"], "batch-ops-pending")
    r = client.post(
        "/ops/raw-signals/process-pending",
        headers=_admin_header(),
        json={"limit": 10, "processing_version": "gate5c_v1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["data"]["completed"] >= 1
    assert data["data"]["processing_version"] == "gate5c_v1"


def test_ops_process_single_batch_happy_path(client: TestClient, admin_env, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-ops-single")
    r = client.post(
        f"/ops/raw-signals/process/{batch_id}",
        headers=_admin_header(),
        json={"processing_version": "gate5c_v1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["data"]["batch_id"] == batch_id
    assert data["data"]["processing_status"] == "completed"
    assert data["data"]["processing_version"] == "gate5c_v1"
