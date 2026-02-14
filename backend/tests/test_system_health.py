# backend/tests/test_system_health.py – Freeze B1 GET /health
"""Minimal test: GET /health returns 200 and ok=true with expected keys."""
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_returns_200_and_ok_true():
    """GET /health returns 200 and JSON with ok=true, version, env, db, timestamp."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "version" in data
    assert data.get("env") in ("prod", "dev")
    assert data.get("db") in ("ok", "error")
    assert "timestamp" in data
