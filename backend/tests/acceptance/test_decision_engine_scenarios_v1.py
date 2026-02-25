"""
Acceptance scenarios for V1 Decision Engine canonical outputs.

Focus: deterministic decision payloads (no FCM dependency).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _evaluate(client: TestClient, event: dict) -> dict:
    response = client.post("/decision/evaluate", json={"event": event})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    return body.get("decision") or {}


def test_hr_high_rest_returns_canonical_alert_code(client: TestClient) -> None:
    decision = _evaluate(
        client,
        {
            "event_type": "heart_rate",
            "payload": {"bpm": 120, "context": "rest"},
        },
    )
    assert decision["decision"] == "notify"
    assert decision["severity"] == "high"
    assert decision["alert_code"] == "heart_rate_high"
    assert decision["rule_id"] == "HR_HIGH_REST"
    assert decision["priority"] == 1


def test_hr_low_returns_canonical_alert_code(client: TestClient) -> None:
    decision = _evaluate(
        client,
        {
            "event_type": "heart_rate",
            "payload": {"bpm": 45, "context": "rest"},
        },
    )
    assert decision["decision"] == "notify"
    assert decision["severity"] == "high"
    assert decision["alert_code"] == "heart_rate_low"
    assert decision["priority"] == 1


def test_bp_high_returns_canonical_alert_code(client: TestClient) -> None:
    decision = _evaluate(
        client,
        {
            "event_type": "blood_pressure",
            "payload": {"sys": 170, "dia": 112},
        },
    )
    assert decision["decision"] == "notify"
    assert decision["severity"] == "high"
    assert decision["alert_code"] == "blood_pressure_high"
    assert decision["priority"] == 1


def test_glucose_high_returns_canonical_alert_code(client: TestClient) -> None:
    decision = _evaluate(
        client,
        {
            "event_type": "glucose",
            "payload": {"glucose_mg_dl": 260},
        },
    )
    assert decision["decision"] == "notify"
    assert decision["severity"] == "high"
    assert decision["alert_code"] == "glucose_high"
    assert decision["priority"] == 1


def test_glucose_low_returns_canonical_alert_code(client: TestClient) -> None:
    decision = _evaluate(
        client,
        {
            "event_type": "glucose",
            "payload": {"glucose_mg_dl": 50},
        },
    )
    assert decision["decision"] == "notify"
    assert decision["severity"] == "high"
    assert decision["alert_code"] == "glucose_low"
    assert decision["priority"] == 1


def test_temperature_high_returns_canonical_alert_code(client: TestClient) -> None:
    decision = _evaluate(
        client,
        {
            "event_type": "temperature",
            "payload": {"temperature_c": 39.2},
        },
    )
    assert decision["decision"] == "notify"
    assert decision["severity"] == "high"
    assert decision["alert_code"] == "temperature_high"
    assert decision["priority"] == 1
