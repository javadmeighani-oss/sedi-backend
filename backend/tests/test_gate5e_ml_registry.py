"""Gate 5-E — ML model registry tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.models import User

_TEST_ADMIN_TOKEN = "test-gate5e-admin"


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-ADMIN-TOKEN": token}


def test_admin_auth_required(client: TestClient):
    r = client.get("/ops/ml/models")
    assert r.status_code == 403


def test_create_model(client: TestClient, admin_env):
    r = client.post(
        "/ops/ml/models",
        headers=_admin_header(),
        json={
            "model_name": "test_model",
            "model_version": "1.0.0",
            "signal_family": "ecg",
            "input_type": "raw_signal_features",
            "status": "research",
        },
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["model_name"] == "test_model"
    assert data["status"] == "research"


def test_list_and_get_model(client: TestClient, admin_env):
    create = client.post(
        "/ops/ml/models",
        headers=_admin_header(),
        json={
            "model_name": "list_model",
            "model_version": "1.0.0",
            "signal_family": "heart",
            "input_type": "raw_signal_features",
        },
    )
    model_id = create.json()["data"]["id"]

    listed = client.get("/ops/ml/models", headers=_admin_header())
    assert listed.status_code == 200
    assert listed.json()["data"]["count"] >= 1

    got = client.get(f"/ops/ml/models/{model_id}", headers=_admin_header())
    assert got.status_code == 200
    assert got.json()["data"]["id"] == model_id


def test_duplicate_model_version_rejected(client: TestClient, admin_env):
    body = {
        "model_name": "dup_model",
        "model_version": "1.0.0",
        "signal_family": "ecg",
        "input_type": "raw_signal_features",
    }
    assert client.post("/ops/ml/models", headers=_admin_header(), json=body).status_code == 201
    r = client.post("/ops/ml/models", headers=_admin_header(), json=body)
    assert r.status_code == 409


def test_invalid_status_rejected(client: TestClient, admin_env):
    r = client.post(
        "/ops/ml/models",
        headers=_admin_header(),
        json={
            "model_name": "bad_status",
            "model_version": "1.0.0",
            "signal_family": "ecg",
            "input_type": "raw_signal_features",
            "status": "production_ready",
        },
    )
    assert r.status_code == 400


def test_active_status_rejected(client: TestClient, admin_env):
    r = client.post(
        "/ops/ml/models",
        headers=_admin_header(),
        json={
            "model_name": "active_model",
            "model_version": "1.0.0",
            "signal_family": "ecg",
            "input_type": "raw_signal_features",
            "status": "active",
        },
    )
    assert r.status_code == 422
