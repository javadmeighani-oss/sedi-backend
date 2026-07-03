"""Gate 5-D — Controlled raw signal processing operations tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

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
from backend.app.services.gate5.raw_signal_feature_extraction import (
    process_pending_raw_signal_batches,
    process_raw_signal_batch,
)
from backend.app.services.gate5.raw_signal_ingestion import build_raw_signal_dedupe_key
from backend.app.services.gate5.raw_signal_processing_flags import (
    ABSOLUTE_MAX_LIMIT,
    DEFAULT_MAX_LIMIT,
    raw_signal_processing_enabled,
    raw_signal_processing_max_limit,
)

_TEST_ADMIN_TOKEN = "test-gate5d-admin"


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-ADMIN-TOKEN": token}


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    monkeypatch.delenv("SEDI_RAW_SIGNAL_PROCESSING_MAX_LIMIT", raising=False)


@pytest.fixture
def user(db):
    u = User(name="Gate5D Owner", secret_key="pw", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _register_hub(client: TestClient, user_id: int, device_id: str = "hub-g5d-001") -> dict:
    r = client.post(
        "/devices/register",
        json={"device_id": device_id, "device_type": GADGET_HUB_DEVICE_TYPE},
        headers=_auth_header(user_id),
    )
    assert r.status_code == 200
    return r.json()["data"]


def _sync_ecg_sensor(client: TestClient, token: str, device_id: str, sensor_key: str = "chest-ecg-g5d") -> None:
    r = client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": device_id,
            "sensors": [{"sensor_key": sensor_key, "sensor_type": "ecg", "connection_status": "connected"}],
        },
    )
    assert r.status_code == 200


@pytest.fixture
def hub_with_ecg(client: TestClient, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    reg = _register_hub(client, user.id)
    _sync_ecg_sensor(client, reg["token"], "hub-g5d-001")
    return reg


def _raw_batch_body(client_batch_id: str = "batch-g5d-001") -> dict:
    started = datetime(2026, 7, 3, 8, 0, 0)
    ended = started + timedelta(seconds=8.0)
    return {
        "device_id": "hub-g5d-001",
        "sensor_key": "chest-ecg-g5d",
        "client_batch_id": client_batch_id,
        "signal_type": "ecg",
        "sample_rate_hz": 250.0,
        "started_at": started.isoformat() + "Z",
        "ended_at": ended.isoformat() + "Z",
        "sample_count": 4,
        "samples": [1024.0, 1025.0, 1023.0, 1022.0],
        "metadata": {"sample_unit": "adc_counts", "compression": "none"},
        "quality_metadata": {"lead_off": False, "motion_detected": False},
    }


def _ingest_batch(client: TestClient, token: str, client_batch_id: str = "batch-g5d-001") -> int:
    r = client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json=_raw_batch_body(client_batch_id=client_batch_id),
    )
    assert r.status_code == 201
    return r.json()["data"]["batch_id"]


def _samples_transient_failure():
    """Empty samples cause SAMPLES_EMPTY on process; valid JSON for Postgres."""
    return []


def _insert_batch_row(
    db,
    *,
    user_id: int,
    hub: Device,
    sensor: DeviceSensor,
    client_batch_id: str,
    samples,
    storage_backend: str = "postgres_json",
) -> RawSignalBatch:
    started = datetime(2026, 7, 3, 8, 0, 0)
    ended = started + timedelta(seconds=8.0)
    now = datetime.utcnow()
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
        sample_count=len(samples),
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


def _hub_sensor(db):
    hub = db.query(Device).filter(Device.device_id == "hub-g5d-001").first()
    sensor = db.query(DeviceSensor).filter(DeviceSensor.sensor_key == "chest-ecg-g5d").first()
    return hub, sensor


def _response_text_has_no_forbidden_payload(payload: object) -> None:
    text = json.dumps(payload).lower()
    for term in ("samples_json", "features_json", "quality_json", "metadata_json", "quality_metadata_json"):
        assert term not in text


# --- Auth ---


def test_admin_auth_fail_closed_when_admin_token_unset(client: TestClient, monkeypatch, hub_with_ecg):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    r = client.post("/ops/raw-signals/process-pending", json={"limit": 1}, headers=_admin_header())
    assert r.status_code == 403
    assert r.json()["detail"] == "admin_disabled"


def test_wrong_admin_token_rejected(client: TestClient, admin_env, hub_with_ecg):
    r = client.post(
        "/ops/raw-signals/process-pending",
        json={"limit": 1},
        headers={"X-ADMIN-TOKEN": "wrong-token"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden"


def test_missing_admin_token_rejected(client: TestClient, admin_env, hub_with_ecg):
    r = client.post("/ops/raw-signals/process-pending", json={"limit": 1})
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden"


# --- Dry run ---


def test_dry_run_creates_no_feature_rows(client: TestClient, admin_env, hub_with_ecg, db):
    _ingest_batch(client, hub_with_ecg["token"], "batch-dry-run")
    before = db.query(RawSignalBatchFeature).count()
    r = client.post(
        "/ops/raw-signals/process-pending",
        headers=_admin_header(),
        json={"limit": 10, "dry_run": True},
    )
    assert r.status_code == 200
    assert db.query(RawSignalBatchFeature).count() == before


def test_dry_run_returns_candidate_batch_ids(client: TestClient, admin_env, user, hub_with_ecg, db):
    hub, sensor = _hub_sensor(db)
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-dry-candidate",
        samples=[1.0, 2.0, 3.0],
    )
    r = client.post(
        "/ops/raw-signals/process-pending",
        headers=_admin_header(),
        json={"limit": 10, "dry_run": True},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dry_run"] is True
    assert data["processed"] == 0
    assert batch.id in data["candidate_batch_ids"]


# --- Limit enforcement ---


def test_request_limit_above_effective_max_returns_400(client: TestClient, admin_env, hub_with_ecg):
    r = client.post(
        "/ops/raw-signals/process-pending",
        headers=_admin_header(),
        json={"limit": 11},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LIMIT_EXCEEDS_MAX"


def test_effective_max_default_is_10(monkeypatch):
    monkeypatch.delenv("SEDI_RAW_SIGNAL_PROCESSING_MAX_LIMIT", raising=False)
    assert raw_signal_processing_max_limit() == DEFAULT_MAX_LIMIT
    assert DEFAULT_MAX_LIMIT == 10


def test_hard_cap_never_exceeds_25_even_if_env_says_100(monkeypatch):
    monkeypatch.setenv("SEDI_RAW_SIGNAL_PROCESSING_MAX_LIMIT", "100")
    assert raw_signal_processing_max_limit() == DEFAULT_MAX_LIMIT
    assert raw_signal_processing_max_limit() <= ABSOLUTE_MAX_LIMIT


# --- Pending behavior ---


def test_completed_batches_skipped_by_pending(client: TestClient, db, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-completed-skip")
    process_raw_signal_batch(db, batch_id)
    summary = process_pending_raw_signal_batches(db, limit=10)
    assert summary.processed == 0


def test_failed_batches_excluded_from_process_pending(client: TestClient, db, user, hub_with_ecg):
    hub, sensor = _hub_sensor(db)
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-failed-excluded",
        samples=[1.0, 2.0],
        storage_backend="object_storage",
    )
    process_raw_signal_batch(db, batch.id)
    summary = process_pending_raw_signal_batches(db, limit=10)
    assert summary.processed == 0


def test_pending_runner_does_not_retry_failed_rows(client: TestClient, db, user, hub_with_ecg):
    hub, sensor = _hub_sensor(db)
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-no-retry-pending",
        samples=_samples_transient_failure(),
    )
    first = process_raw_signal_batch(db, batch.id)
    assert first.processing_status == "failed"
    batch.samples_json = [1.0, 2.0, 3.0]
    db.add(batch)
    db.commit()
    summary = process_pending_raw_signal_batches(db, limit=10)
    assert summary.processed == 0
    row = db.query(RawSignalBatchFeature).filter(RawSignalBatchFeature.raw_signal_batch_id == batch.id).one()
    assert row.processing_status == "failed"


# --- Single batch retry ---


def test_single_batch_failed_retry_default_false_returns_existing_failed(client: TestClient, db, user, hub_with_ecg):
    hub, sensor = _hub_sensor(db)
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-retry-default-false",
        samples=_samples_transient_failure(),
    )
    first = process_raw_signal_batch(db, batch.id, allow_retry=False)
    assert first.processing_status == "failed"
    batch.samples_json = [1.0, 2.0, 3.0]
    db.add(batch)
    db.commit()
    second = process_raw_signal_batch(db, batch.id, allow_retry=False)
    assert second.skipped is True
    assert second.processing_status == "failed"
    assert second.feature_id == first.feature_id


def test_single_batch_allow_retry_true_retries_transient_failed(client: TestClient, db, user, hub_with_ecg):
    hub, sensor = _hub_sensor(db)
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-retry-transient",
        samples=_samples_transient_failure(),
    )
    first = process_raw_signal_batch(db, batch.id, allow_retry=False)
    assert first.processing_status == "failed"
    batch.samples_json = [10.0, 11.0, 12.0]
    db.add(batch)
    db.commit()
    second = process_raw_signal_batch(db, batch.id, allow_retry=True)
    assert second.skipped is False
    assert second.processing_status == "completed"


def test_object_storage_not_supported_does_not_retry_even_with_allow_retry(
    client: TestClient, db, user, hub_with_ecg
):
    hub, sensor = _hub_sensor(db)
    batch = _insert_batch_row(
        db,
        user_id=user.id,
        hub=hub,
        sensor=sensor,
        client_batch_id="batch-permanent-fail",
        samples=[1.0, 2.0],
        storage_backend="object_storage",
    )
    first = process_raw_signal_batch(db, batch.id)
    assert first.processing_status == "failed"
    second = process_raw_signal_batch(db, batch.id, allow_retry=True)
    assert second.skipped is True
    assert second.error_code == "OBJECT_STORAGE_NOT_SUPPORTED"


# --- No raw samples in responses ---


def test_no_raw_samples_in_pending_response(client: TestClient, admin_env, hub_with_ecg):
    _ingest_batch(client, hub_with_ecg["token"], "batch-no-samples-pending")
    r = client.post(
        "/ops/raw-signals/process-pending",
        headers=_admin_header(),
        json={"limit": 10, "dry_run": True},
    )
    assert r.status_code == 200
    _response_text_has_no_forbidden_payload(r.json())


def test_no_raw_samples_in_single_response(client: TestClient, admin_env, hub_with_ecg):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-no-samples-single")
    r = client.post(
        f"/ops/raw-signals/process/{batch_id}",
        headers=_admin_header(),
        json={},
    )
    assert r.status_code == 200
    _response_text_has_no_forbidden_payload(r.json())


def test_no_raw_samples_features_quality_in_status_response(client: TestClient, admin_env, hub_with_ecg, db):
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-status-safe")
    process_raw_signal_batch(db, batch_id)
    r = client.get(
        f"/ops/raw-signals/status/{batch_id}",
        headers=_admin_header(),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["has_batch"] is True
    assert data["processing_status"] == "completed"
    _response_text_has_no_forbidden_payload(r.json())


# --- No side effects ---


def test_no_notification_rows_created(client: TestClient, db, user, hub_with_ecg):
    before = db.query(Notification).filter(Notification.user_id == user.id).count()
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-no-notif-g5d")
    process_raw_signal_batch(db, batch_id)
    after = db.query(Notification).filter(Notification.user_id == user.id).count()
    assert after == before


def test_no_device_event_rows_created(client: TestClient, db, user, hub_with_ecg):
    before = db.query(DeviceEvent).filter(DeviceEvent.user_id == user.id).count()
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-no-event-g5d")
    process_raw_signal_batch(db, batch_id)
    after = db.query(DeviceEvent).filter(DeviceEvent.user_id == user.id).count()
    assert after == before


def test_no_user_memory_facts_created(client: TestClient, db, user, hub_with_ecg):
    before = db.query(UserMemoryFact).filter(UserMemoryFact.user_id == user.id).count()
    batch_id = _ingest_batch(client, hub_with_ecg["token"], "batch-no-memory-g5d")
    process_raw_signal_batch(db, batch_id)
    after = db.query(UserMemoryFact).filter(UserMemoryFact.user_id == user.id).count()
    assert after == before


# --- Scheduler ---


def test_scheduler_default_off_flag_unset(monkeypatch):
    monkeypatch.delenv("SEDI_RAW_SIGNAL_PROCESSING_ENABLED", raising=False)
    assert raw_signal_processing_enabled() is False


def test_scheduler_job_not_registered_when_disabled(monkeypatch):
    monkeypatch.delenv("SEDI_RAW_SIGNAL_PROCESSING_ENABLED", raising=False)
    import backend.app.core.scheduler as sched_mod

    added_job_ids: list[str] = []
    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    def _capture_add_job(*_args, **kwargs):
        added_job_ids.append(kwargs.get("id", ""))

    mock_scheduler.add_job = _capture_add_job
    with patch.object(sched_mod, "scheduler", mock_scheduler):
        sched_mod.start_scheduler()
    assert "raw_signal_processing" not in added_job_ids


def test_scheduler_enabled_smoke_respects_limit_and_no_side_effects(
    client: TestClient, db, user, hub_with_ecg, monkeypatch
):
    monkeypatch.setenv("SEDI_RAW_SIGNAL_PROCESSING_ENABLED", "true")
    monkeypatch.setenv("SEDI_RAW_SIGNAL_PROCESSING_MAX_LIMIT", "1")
    hub, sensor = _hub_sensor(db)
    for i in range(2):
        _insert_batch_row(
            db,
            user_id=user.id,
            hub=hub,
            sensor=sensor,
            client_batch_id=f"batch-sched-{i}",
            samples=[1.0, 2.0, 3.0],
        )
    notif_before = db.query(Notification).count()
    event_before = db.query(DeviceEvent).count()
    memory_before = db.query(UserMemoryFact).count()

    import backend.app.core.scheduler as sched_mod

    with patch("backend.app.core.scheduler.get_db") as mock_get_db:
        mock_get_db.return_value = iter([db])
        sched_mod.run_raw_signal_processing()

    features = db.query(RawSignalBatchFeature).count()
    assert features == 1
    assert db.query(Notification).count() == notif_before
    assert db.query(DeviceEvent).count() == event_before
    assert db.query(UserMemoryFact).count() == memory_before
