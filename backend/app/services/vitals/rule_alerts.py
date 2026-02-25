# app/services/vitals/rule_alerts.py
"""
Rule-based Alerts for Vitals (Release C3)

Conservative thresholds; no AI dependency.
Only computes alert actions; does not persist. Persistence is done by the
Decision Engine action executor (device_ingestion -> evaluate_event -> execute).
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.app.decision_engine.models import CreateHealthAlertAction


def compute_alert_actions(
    user_id: int,
    event_type: str,
    normalized_payload: Dict[str, Any],
) -> List[CreateHealthAlertAction]:
    """
    Return health_alert actions if normalized vitals are outside conservative thresholds.
    No side effects; caller is responsible for executing actions (e.g. via notification_engine).
    """
    out: List[CreateHealthAlertAction] = []
    try:
        if event_type == "heart_rate":
            bpm = float(normalized_payload["bpm"])
            a = _hr_alert(user_id, bpm)
            if a is not None:
                out.append(a)

        elif event_type == "blood_pressure":
            sys = float(normalized_payload["sys"])
            dia = float(normalized_payload["dia"])
            a = _bp_alert(user_id, sys, dia)
            if a is not None:
                out.append(a)

        elif event_type == "glucose":
            mg = float(normalized_payload["glucose_mg_dl"])
            a = _glucose_alert(user_id, mg)
            if a is not None:
                out.append(a)

        elif event_type == "temperature":
            c = float(normalized_payload["temperature_c"])
            a = _temp_alert(user_id, c)
            if a is not None:
                out.append(a)
    except (KeyError, TypeError, ValueError):
        pass
    return out


def _hr_alert(user_id: int, bpm: float) -> CreateHealthAlertAction | None:
    # soft: <50 or >120; hard: <40 or >160
    if bpm < 40:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="heart_rate_low",
            alert_reason="Your heart rate looks very low right now. If you feel unwell, please check in with someone you trust.",
            priority="critical",
        )
    if bpm < 50:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="heart_rate_low",
            alert_reason="Your heart rate seems a bit low. Please take it easy and check how you feel.",
            priority="high",
        )
    if bpm > 160:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="heart_rate_high",
            alert_reason="Your heart rate looks very high right now. Please pause, sit down, and check how you feel.",
            priority="critical",
        )
    if bpm > 120:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="heart_rate_high",
            alert_reason="Your heart rate seems elevated. Please slow down, breathe, and see if it settles.",
            priority="high",
        )
    return None


def _bp_alert(user_id: int, sys: float, dia: float) -> CreateHealthAlertAction | None:
    if sys >= 180 or dia >= 120:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="blood_pressure_high",
            alert_reason="Your blood pressure reading looks very high. Please pause, rest for a moment, and consider rechecking soon.",
            priority="critical",
        )
    if sys >= 140 or dia >= 90:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="blood_pressure_high",
            alert_reason="Your blood pressure reading seems high. Please take it easy and consider rechecking when you're calm.",
            priority="high",
        )
    return None


def _glucose_alert(user_id: int, mg_dl: float) -> CreateHealthAlertAction | None:
    if mg_dl < 54:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="glucose_low",
            alert_reason="Your glucose looks very low. If you feel shaky or unwell, please check in and consider rechecking soon.",
            priority="critical",
        )
    if mg_dl < 70:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="glucose_low",
            alert_reason="Your glucose seems low. Please pay attention to how you feel and consider rechecking soon.",
            priority="high",
        )
    if mg_dl > 250:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="glucose_high",
            alert_reason="Your glucose looks very high. Please take a calm moment and consider rechecking soon.",
            priority="critical",
        )
    if mg_dl > 180:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="glucose_high",
            alert_reason="Your glucose seems elevated. Please drink some water and consider rechecking soon.",
            priority="high",
        )
    return None


def _temp_alert(user_id: int, c: float) -> CreateHealthAlertAction | None:
    if c < 34:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="low_temperature",
            alert_reason="Your temperature looks very low. Please warm up and check how you feel.",
            priority="critical",
        )
    if c < 35.5:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="low_temperature",
            alert_reason="Your temperature seems low. Please keep warm and consider rechecking soon.",
            priority="high",
        )
    if c > 39.5:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="temperature_high",
            alert_reason="Your temperature looks very high. Please rest, sip water, and consider rechecking soon.",
            priority="critical",
        )
    if c > 38.0:
        return CreateHealthAlertAction(
            user_id=user_id,
            alert_code="temperature_high",
            alert_reason="Your temperature seems elevated. Please rest and consider rechecking soon.",
            priority="high",
        )
    return None
