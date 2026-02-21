# backend/tests/test_observability_v1.py – V1 Pilot observability endpoints
"""Minimal tests: GET /notifications/admin/observability (admin protection)."""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

# Module-level client for tests that do not need db override (e.g. 401 without db)
_client_no_db = TestClient(app)


def test_observability_with_admin_token_and_header_returns_200(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """With ADMIN_TOKEN set and valid X-Admin-Token header, GET /notifications/admin/observability returns 200 and ok=true."""
    monkeypatch.setenv("ADMIN_TOKEN", "test-observability-admin-token")
    r = client.get(
        "/notifications/admin/observability",
        params={"minutes": 60},
        headers={"X-Admin-Token": "test-observability-admin-token"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert "data" in data
    assert "window_minutes" in data["data"]
    assert "now_utc" in data["data"]
    assert "notifications_created_total" in data["data"]
    assert "delivery_health" in data["data"]


def test_observability_without_header_returns_401_when_admin_token_set(
    monkeypatch: pytest.MonkeyPatch,
):
    """When ADMIN_TOKEN is set, request without X-Admin-Token returns 401."""
    monkeypatch.setenv("ADMIN_TOKEN", "test-observability-admin-token")
    r = _client_no_db.get("/notifications/admin/observability", params={"minutes": 60})
    assert r.status_code == 401
