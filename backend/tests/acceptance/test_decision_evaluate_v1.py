"""
Acceptance tests for POST /decision/evaluate (Decision Engine V1).

Source of truth: backend/docs/contracts/v1/decision.md
- Envelope: { "ok": true, "decision": { ... } } (no data/error wrapper).
- Tests use controlled payloads only; no DB dependency; deterministic.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


# ---------- Helpers ----------

def _post_evaluate(client: TestClient, event: dict) -> dict:
    """POST /decision/evaluate and return JSON body."""
    response = client.post("/decision/evaluate", json={"event": event})
    assert response.status_code == 200, response.text
    return response.json()


def _event_base(user_id: int = 1, device_id: str = "Sedi001", recorded_at: str = "2025-02-22T12:00:00Z") -> dict:
    return {
        "user_id": user_id,
        "device_id": device_id,
        "recorded_at": recorded_at,
    }


# ---------- Contract envelope and structure ----------

def test_evaluate_returns_v1_envelope(client: TestClient) -> None:
    """Response must have ok and decision (no data/error wrapper)."""
    event = {
        **_event_base(),
        "event_type": "heart_rate",
        "payload": {"bpm": 140},
    }
    body = _post_evaluate(client, event)
    assert "ok" in body
    assert body["ok"] is True
    assert "decision" in body
    assert "data" not in body or body.get("data") is None
    dec = body["decision"]
    # Implementation returns: decision, reason, severity, source_event_id, meta
    assert "reason" in dec
    assert "decision" in dec  # outcome equivalent


# ---------- Scenarios (contract example + rule-driven) ----------

def test_evaluate_heart_rate_high_contract_example(client: TestClient) -> None:
    """Contract example: heart_rate with payload.bpm 140 -> 200 and decision structure."""
    event = {
        **_event_base(),
        "event_type": "heart_rate",
        "payload": {"bpm": 140},
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert dec["reason"] is not None
    assert dec["decision"] in ("none", "notify", "store_only")
    if "meta" in dec:
        assert isinstance(dec["meta"], dict)


def test_evaluate_heart_rate_high_rule_match(client: TestClient) -> None:
    """Heart rate high (rule HR_HIGH_REST): event with bpm>110 and context=rest -> notify."""
    event = {
        **_event_base(),
        "event_type": "heart_rate",
        "bpm": 140,
        "context": "rest",
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert dec["decision"] == "notify"
    assert dec["reason"] == "HR_HIGH_REST"
    assert "severity" in dec
    assert "meta" in dec


def test_evaluate_heart_rate_high_payload_bpm_context(client: TestClient) -> None:
    """HR_HIGH_REST via payload.bpm and payload.context (normalized before rules)."""
    event = {
        "event_type": "heart_rate",
        "payload": {"bpm": 140, "context": "rest"},
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert dec["decision"] == "notify"
    assert dec["reason"] == "HR_HIGH_REST"


def test_evaluate_heart_rate_low(client: TestClient) -> None:
    """Heart rate low scenario: payload.bpm low; assert 200 and decision structure."""
    event = {
        **_event_base(),
        "event_type": "heart_rate",
        "payload": {"bpm": 45},
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert "reason" in dec
    assert dec["decision"] in ("none", "notify", "store_only")


def test_evaluate_blood_pressure_high(client: TestClient) -> None:
    """Blood pressure high scenario: assert 200 and decision structure."""
    event = {
        **_event_base(),
        "event_type": "blood_pressure",
        "payload": {"sys": 170, "dia": 100},
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert "reason" in dec
    assert dec["decision"] in ("none", "notify", "store_only")


def test_evaluate_glucose_high(client: TestClient) -> None:
    """Glucose high scenario: assert 200 and decision structure."""
    event = {
        **_event_base(),
        "event_type": "glucose",
        "payload": {"glucose_mg_dl": 250},
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert "reason" in dec
    assert dec["decision"] in ("none", "notify", "store_only")


def test_evaluate_glucose_low(client: TestClient) -> None:
    """Glucose low scenario: assert 200 and decision structure."""
    event = {
        **_event_base(),
        "event_type": "glucose",
        "payload": {"glucose_mg_dl": 50},
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert "reason" in dec
    assert dec["decision"] in ("none", "notify", "store_only")


def test_evaluate_temperature_high(client: TestClient) -> None:
    """Temperature high scenario: assert 200 and decision structure."""
    event = {
        **_event_base(),
        "event_type": "temperature",
        "payload": {"temperature_c": 39.5},
    }
    body = _post_evaluate(client, event)
    assert body["ok"] is True
    dec = body["decision"]
    assert "reason" in dec
    assert dec["decision"] in ("none", "notify", "store_only")


# ---------- Validation error ----------

def test_evaluate_invalid_payload_returns_422(client: TestClient) -> None:
    """Invalid payload: missing required 'event' -> 422."""
    response = client.post("/decision/evaluate", json={})
    assert response.status_code == 422
