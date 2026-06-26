import pytest
from fastapi.testclient import TestClient


def test_ops_status_admin_token_unset_returns_403(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    res = client.get("/ops/status")
    assert res.status_code == 403
    assert res.json().get("detail") == "admin_disabled"


def test_ops_status_wrong_admin_token_returns_403(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_TOKEN", "x")
    res = client.get("/ops/status", headers={"X-ADMIN-TOKEN": "wrong"})
    assert res.status_code == 403
    assert res.json().get("detail") == "forbidden"


def test_ops_status_valid_admin_token_returns_200(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_TOKEN", "x")
    res = client.get("/ops/status", headers={"X-ADMIN-TOKEN": "x"})
    assert res.status_code == 200, res.text

    body = res.json()
    assert body.get("ok") is True
    data = body.get("data")
    assert isinstance(data, dict)
    assert "service" in data
    assert "db" in data
    assert "runtime" in data

    counts = data.get("counts")
    assert isinstance(counts, dict)
    pending = counts.get("notifications_pending")
    failed_24h = counts.get("notifications_failed_24h")
    events_24h = counts.get("device_events_24h")
    assert isinstance(pending, int)
    assert failed_24h is None or isinstance(failed_24h, int)
    assert events_24h is None or isinstance(events_24h, int)


def test_ops_config_sms_returns_set_unset(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """GET /ops/config/sms returns set/unset for SMS vars (no secret values)."""
    monkeypatch.setenv("ADMIN_TOKEN", "ops-admin")
    monkeypatch.setenv("SMS_DISABLED", "false")
    monkeypatch.setenv("SMS_PROVIDER", "mediana")
    monkeypatch.setenv("MEDIANA_API_KEY", "secret-key-never-shown")
    monkeypatch.setenv("MEDIANA_OTP_PATTERN_CODE", "test-pattern")
    res = client.get("/ops/config/sms", headers={"X-ADMIN-TOKEN": "ops-admin"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    data = body.get("data")
    assert data["SMS_DISABLED"] == "set"
    assert data["SMS_PROVIDER"] == "set"
    assert data["MEDIANA_API_KEY"] == "set"
    assert data["MEDIANA_OTP_PATTERN_CODE"] == "set"
    assert "secret" not in str(body).lower()  # No raw key in response
