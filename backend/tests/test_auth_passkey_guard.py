# backend/tests/test_auth_passkey_guard.py – A3.1 passkey disabled in prod
"""Minimal tests: passkey endpoints return 404 when ENV=prod or DEBUG=false."""
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_passkey_endpoints_404_when_env_prod(monkeypatch):
    """When ENV=prod, set-passkey and verify-passkey return 404 (no passkey in query used)."""
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DEBUG", "false")
    r_set = client.post("/auth/set-passkey", params={"user_id": 1, "passkey": "x"})
    r_verify = client.post("/auth/verify-passkey", params={"user_id": 1, "passkey": "x"})
    assert r_set.status_code == 404
    assert r_verify.status_code == 404


def test_passkey_endpoints_404_when_debug_false(monkeypatch):
    """When DEBUG=false (and ENV not prod), passkey endpoints still disabled for V1."""
    monkeypatch.setenv("ENV", "")
    monkeypatch.setenv("DEBUG", "false")
    r = client.post("/auth/set-passkey", params={"user_id": 1, "passkey": "x"})
    assert r.status_code == 404
