# app/services/vitals/rule_alerts.py
"""
Rule-based Alerts for Vitals (Release C3)

Conservative thresholds; no AI dependency.
Creates health_alert notifications via DecisionEngine.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.services.notification_engine import DecisionEngine


def maybe_create_alert(
    db: Session,
    user_id: int,
    event_type: str,
    normalized_payload: Dict[str, Any],
) -> None:
    """
    Create health_alert notification if normalized vitals are outside conservative thresholds.
    Best-effort: never raises.
    """
    try:
        engine = DecisionEngine(db)

        if event_type == "heart_rate":
            bpm = float(normalized_payload["bpm"])
            _hr_alert(engine, user_id, bpm)
            return

        if event_type == "blood_pressure":
            sys = float(normalized_payload["sys"])
            dia = float(normalized_payload["dia"])
            _bp_alert(engine, user_id, sys, dia)
            return

        if event_type == "glucose":
            mg = float(normalized_payload["glucose_mg_dl"])
            _glucose_alert(engine, user_id, mg)
            return

        if event_type == "temperature":
            c = float(normalized_payload["temperature_c"])
            _temp_alert(engine, user_id, c)
            return
    except Exception:
        return


def _hr_alert(engine: DecisionEngine, user_id: int, bpm: float) -> None:
    # soft: <50 or >120; hard: <40 or >160
    if bpm < 40:
        engine.create_health_alert(user_id=user_id, alert_code="low_heart_rate", alert_reason="Your heart rate looks very low right now. If you feel unwell, please check in with someone you trust.", priority="critical")
    elif bpm < 50:
        engine.create_health_alert(user_id=user_id, alert_code="low_heart_rate", alert_reason="Your heart rate seems a bit low. Please take it easy and check how you feel.", priority="high")
    elif bpm > 160:
        engine.create_health_alert(user_id=user_id, alert_code="high_heart_rate", alert_reason="Your heart rate looks very high right now. Please pause, sit down, and check how you feel.", priority="critical")
    elif bpm > 120:
        engine.create_health_alert(user_id=user_id, alert_code="high_heart_rate", alert_reason="Your heart rate seems elevated. Please slow down, breathe, and see if it settles.", priority="high")


def _bp_alert(engine: DecisionEngine, user_id: int, sys: float, dia: float) -> None:
    # soft: sys>=140 or dia>=90; hard: sys>=180 or dia>=120
    if sys >= 180 or dia >= 120:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="high_blood_pressure",
            alert_reason="Your blood pressure reading looks very high. Please pause, rest for a moment, and consider rechecking soon.",
            priority="critical",
        )
    elif sys >= 140 or dia >= 90:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="high_blood_pressure",
            alert_reason="Your blood pressure reading seems high. Please take it easy and consider rechecking when you're calm.",
            priority="high",
        )


def _glucose_alert(engine: DecisionEngine, user_id: int, mg_dl: float) -> None:
    # soft: <70 or >180; hard: <54 or >250
    if mg_dl < 54:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="low_glucose",
            alert_reason="Your glucose looks very low. If you feel shaky or unwell, please check in and consider rechecking soon.",
            priority="critical",
        )
    elif mg_dl < 70:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="low_glucose",
            alert_reason="Your glucose seems low. Please pay attention to how you feel and consider rechecking soon.",
            priority="high",
        )
    elif mg_dl > 250:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="high_glucose",
            alert_reason="Your glucose looks very high. Please take a calm moment and consider rechecking soon.",
            priority="critical",
        )
    elif mg_dl > 180:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="high_glucose",
            alert_reason="Your glucose seems elevated. Please drink some water and consider rechecking soon.",
            priority="high",
        )


def _temp_alert(engine: DecisionEngine, user_id: int, c: float) -> None:
    # soft: <35.5 or >38.0; hard: <34 or >39.5
    if c < 34:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="low_temperature",
            alert_reason="Your temperature looks very low. Please warm up and check how you feel.",
            priority="critical",
        )
    elif c < 35.5:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="low_temperature",
            alert_reason="Your temperature seems low. Please keep warm and consider rechecking soon.",
            priority="high",
        )
    elif c > 39.5:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="high_temperature",
            alert_reason="Your temperature looks very high. Please rest, sip water, and consider rechecking soon.",
            priority="critical",
        )
    elif c > 38.0:
        engine.create_health_alert(
            user_id=user_id,
            alert_code="high_temperature",
            alert_reason="Your temperature seems elevated. Please rest and consider rechecking soon.",
            priority="high",
        )

