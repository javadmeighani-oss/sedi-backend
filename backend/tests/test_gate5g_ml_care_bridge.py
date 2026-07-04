"""Gate 5-G — ML care bridge tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.models import DeviceEvent, InteractionEvent, Notification, User
from backend.app.services.gate5.gadget_hub_status import GADGET_HUB_DEVICE_TYPE
from backend.app.services.gate5.ml_safety import contains_forbidden_user_text
from backend.app.services.gate5.raw_signal_feature_extraction import process_raw_signal_batch

_TEST_ADMIN_TOKEN = "test-gate5g-admin"


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-ADMIN-TOKEN": token}


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    monkeypatch.setenv("SEDI_GATE5_ML_SHADOW_ENABLED", "true")
    monkeypatch.setenv("SEDI_GATE5_ML_PROCESSING_ENABLED", "true")
    monkeypatch.delenv("SEDI_GATE5_ML_CARE_BRIDGE_ENABLED", raising=False)
    monkeypatch.delenv("SEDI_GATE5_ML_NOTIFICATION_ENABLED", raising=False)
    monkeypatch.delenv("SEDI_GATE5_ML_CHAT_CONTEXT_ENABLED", raising=False)
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)


@pytest.fixture
def user(db):
    u = User(name="Care Bridge User", secret_key="pw", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def inference_record(client: TestClient, db, user, admin_env):
    reg = client.post(
        "/devices/register",
        json={"device_id": "hub-care-bridge", "device_type": GADGET_HUB_DEVICE_TYPE},
        headers=_auth_header(user.id),
    )
    token = reg.json()["data"]["token"]
    client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-care-bridge",
            "sensors": [{"sensor_key": "ecg-cb", "sensor_type": "ecg", "connection_status": "connected"}],
        },
    )
    started = datetime(2026, 7, 3, 8, 0, 0)
    ended = started + timedelta(seconds=8.0)
    ingest = client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-care-bridge",
            "sensor_key": "ecg-cb",
            "client_batch_id": "batch-care-bridge-001",
            "signal_type": "ecg",
            "sample_rate_hz": 250.0,
            "started_at": started.isoformat() + "Z",
            "ended_at": ended.isoformat() + "Z",
            "sample_count": 2000,
            "samples": [1024.0 + (i % 5) for i in range(2000)],
        },
    )
    batch_id = ingest.json()["data"]["batch_id"]
    feature = process_raw_signal_batch(db, batch_id)

    baseline = client.post(
        f"/ops/ml/run-baseline/{feature.feature_id}",
        headers=_admin_header(),
    )
    assert baseline.status_code == 200
    record_id = baseline.json()["data"]["inference_record_id"]
    return {"record_id": record_id, "user_id": user.id}


def test_unauthenticated_care_bridge_rejected(client: TestClient, inference_record):
    r = client.post(f"/ops/ml/inference-records/{inference_record['record_id']}/care-bridge/dry-run")
    assert r.status_code == 403


def test_dry_run_safe_suggestion(client: TestClient, admin_env, inference_record, db):
    before_notif = db.query(Notification).count()
    before_events = db.query(DeviceEvent).count()
    before_interactions = db.query(InteractionEvent).count()

    r = client.post(
        f"/ops/ml/inference-records/{inference_record['record_id']}/care-bridge/dry-run",
        headers=_admin_header(),
    )
    assert r.status_code == 200
    text = r.json()["data"]["care_suggestion_text"].lower()
    assert "not a diagnosis" in text
    assert not contains_forbidden_user_text(r.json()["data"]["care_suggestion_text"])
    assert r.json()["data"]["dry_run"] is True
    assert r.json()["data"]["device_event_id"] is None

    assert db.query(Notification).count() == before_notif
    assert db.query(DeviceEvent).count() == before_events
    assert db.query(InteractionEvent).count() == before_interactions


def test_flags_off_block_delivery(client: TestClient, admin_env, inference_record, db):
    before_notif = db.query(Notification).count()
    before_events = db.query(DeviceEvent).count()
    before_interactions = db.query(InteractionEvent).count()

    r = client.post(
        f"/ops/ml/inference-records/{inference_record['record_id']}/care-bridge",
        headers=_admin_header(),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["blocked_reason"] is not None
    assert data["device_event_id"] is None
    assert data["notification_id"] is None
    assert data["interaction_event_id"] is None

    assert db.query(Notification).count() == before_notif
    assert db.query(DeviceEvent).count() == before_events
    assert db.query(InteractionEvent).count() == before_interactions


def test_bridge_creates_device_event_when_enabled(client: TestClient, admin_env, inference_record, db, monkeypatch):
    monkeypatch.setenv("SEDI_GATE5_ML_CARE_BRIDGE_ENABLED", "true")
    before_notif = db.query(Notification).count()

    r = client.post(
        f"/ops/ml/inference-records/{inference_record['record_id']}/care-bridge",
        headers=_admin_header(),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["device_event_id"] is not None
    assert data["notification_id"] is None
    assert data["interaction_event_id"] is None
    assert db.query(Notification).count() == before_notif


def test_notification_only_when_flag_on(client: TestClient, admin_env, inference_record, db, monkeypatch):
    monkeypatch.setenv("SEDI_GATE5_ML_CARE_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("SEDI_GATE5_ML_NOTIFICATION_ENABLED", "true")
    before = db.query(Notification).count()

    r = client.post(
        f"/ops/ml/inference-records/{inference_record['record_id']}/care-bridge",
        headers=_admin_header(),
    )
    assert r.status_code == 200
    assert r.json()["data"]["notification_id"] is not None
    assert db.query(Notification).count() == before + 1
    body = db.query(Notification).order_by(Notification.id.desc()).first().body.lower()
    assert "not a diagnosis" in body
    assert not contains_forbidden_user_text(db.query(Notification).order_by(Notification.id.desc()).first().body)
