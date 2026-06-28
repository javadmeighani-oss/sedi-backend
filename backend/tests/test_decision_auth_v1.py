"""POST /decision/evaluate requires admin token fail-closed (Phase 1G)."""

from __future__ import annotations

_TEST_ADMIN_TOKEN = "test-decision-auth-v1"


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-Admin-Token": token}


def test_decision_evaluate_unset_admin_token_returns_403(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    response = client.post(
        "/decision/evaluate",
        json={"event": {"event_type": "heart_rate", "bpm": 80, "context": "rest"}},
    )
    assert response.status_code == 403
    assert response.json().get("detail") == "admin_disabled"


def test_decision_evaluate_missing_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.post(
        "/decision/evaluate",
        json={"event": {"event_type": "heart_rate", "bpm": 80, "context": "rest"}},
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_decision_evaluate_wrong_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.post(
        "/decision/evaluate",
        json={"event": {"event_type": "heart_rate", "bpm": 80, "context": "rest"}},
        headers=_admin_header("wrong-admin-token"),
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_decision_evaluate_valid_admin_token_returns_200(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.post(
        "/decision/evaluate",
        json={
            "event": {
                "event_type": "heart_rate",
                "bpm": 80,
                "context": "rest",
            }
        },
        headers=_admin_header(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is True
    assert body.get("decision", {}).get("decision") in ("none", "notify", "store_only")
