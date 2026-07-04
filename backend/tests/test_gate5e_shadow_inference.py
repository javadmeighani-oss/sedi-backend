"""Gate 5-E — Shadow ML inference record tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.models import Notification, User, UserMemoryFact
from backend.app.services.gate5.gadget_hub_status import GADGET_HUB_DEVICE_TYPE
from backend.app.services.gate5.raw_signal_feature_extraction import process_raw_signal_batch

_TEST_ADMIN_TOKEN = "test-gate5e-shadow-admin"


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-ADMIN-TOKEN": token}


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    monkeypatch.setenv("SEDI_GATE5_ML_SHADOW_ENABLED", "true")
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)


@pytest.fixture
def user(db):
    u = User(name="ML Shadow User", secret_key="pw", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def hub_feature(db, client, user, admin_env):
    reg = client.post(
        "/devices/register",
        json={"device_id": "hub-ml-shadow", "device_type": GADGET_HUB_DEVICE_TYPE},
        headers=_auth_header(user.id),
    )
    token = reg.json()["data"]["token"]
    client.post(
        "/device/sensors/sync",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-ml-shadow",
            "sensors": [{"sensor_key": "ecg-ml", "sensor_type": "ecg", "connection_status": "connected"}],
        },
    )
    started = datetime(2026, 7, 3, 8, 0, 0)
    ended = started + timedelta(seconds=8.0)
    ingest = client.post(
        "/device/signals/raw",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "device_id": "hub-ml-shadow",
            "sensor_key": "ecg-ml",
            "client_batch_id": "batch-ml-shadow-001",
            "signal_type": "ecg",
            "sample_rate_hz": 250.0,
            "started_at": started.isoformat() + "Z",
            "ended_at": ended.isoformat() + "Z",
            "sample_count": 2000,
            "samples": [1024.0 + (i % 5) for i in range(2000)],
            "metadata": {"sample_unit": "adc_counts"},
        },
    )
    batch_id = ingest.json()["data"]["batch_id"]
    feature = process_raw_signal_batch(db, batch_id)
    model = client.post(
        "/ops/ml/models",
        headers=_admin_header(),
        json={
            "model_name": "shadow_test_model",
            "model_version": "1.0.0",
            "signal_family": "ecg",
            "input_type": "raw_signal_features",
        },
    )
    return {
        "user_id": user.id,
        "batch_id": batch_id,
        "feature_id": feature.feature_id,
        "model_id": model.json()["data"]["id"],
    }


def test_admin_auth_required(client: TestClient):
    r = client.post(
        "/ops/ml/inference-records",
        json={"user_id": 1, "model_id": 1, "output_type": "low_confidence"},
    )
    assert r.status_code == 403


def test_shadow_disabled_by_default(client: TestClient, admin_env, hub_feature, monkeypatch):
    monkeypatch.delenv("SEDI_GATE5_ML_SHADOW_ENABLED", raising=False)
    r = client.post(
        "/ops/ml/inference-records",
        headers=_admin_header(),
        json={
            "user_id": hub_feature["user_id"],
            "model_id": hub_feature["model_id"],
            "output_type": "low_confidence",
            "raw_signal_batch_feature_id": hub_feature["feature_id"],
            "score": 0.2,
            "confidence": 0.3,
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "ml_shadow_disabled"


def test_valid_shadow_inference(client: TestClient, admin_env, hub_feature, db):
    before_notif = db.query(Notification).count()
    before_mem = db.query(UserMemoryFact).count()

    r = client.post(
        "/ops/ml/inference-records",
        headers=_admin_header(),
        json={
            "user_id": hub_feature["user_id"],
            "model_id": hub_feature["model_id"],
            "output_type": "possible_anomaly",
            "raw_signal_batch_feature_id": hub_feature["feature_id"],
            "score": 0.55,
            "confidence": 0.45,
            "features_summary_json": {"std_dev": 210.0},
        },
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["user_visible"] is False
    assert data["output_type"] == "possible_anomaly"
    assert "raw_output_json" not in data

    assert db.query(Notification).count() == before_notif
    assert db.query(UserMemoryFact).count() == before_mem


def test_forbidden_clinical_output_rejected(client: TestClient, admin_env, hub_feature):
    r = client.post(
        "/ops/ml/inference-records",
        headers=_admin_header(),
        json={
            "user_id": hub_feature["user_id"],
            "model_id": hub_feature["model_id"],
            "output_type": "arrhythmia",
            "raw_signal_batch_feature_id": hub_feature["feature_id"],
        },
    )
    assert r.status_code == 422


def test_invalid_feature_id_rejected(client: TestClient, admin_env, hub_feature):
    r = client.post(
        "/ops/ml/inference-records",
        headers=_admin_header(),
        json={
            "user_id": hub_feature["user_id"],
            "model_id": hub_feature["model_id"],
            "output_type": "low_confidence",
            "raw_signal_batch_feature_id": 999999,
        },
    )
    assert r.status_code == 404
