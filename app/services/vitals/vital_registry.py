# app/services/vitals/vital_registry.py
"""
Vital Registry (Release C3)

Schema-driven validation + normalization + mapping for multiple vitals.
No DB required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

from app.services.device_ingestion import build_dedupe_key as _build_dedupe_key_5m


SupportedVital = Literal["heart_rate", "blood_pressure", "glucose", "temperature"]


class VitalValidationError(ValueError):
    """Raised when an event payload is invalid for its event_type."""


@dataclass(frozen=True)
class MemoryUpdate:
    domain: str
    key: str
    value: Any
    confidence: float = 0.9
    source: str = "device"


def _require_int(payload: Dict[str, Any], field: str) -> int:
    if field not in payload:
        raise VitalValidationError(f"Missing required field '{field}'")
    try:
        return int(payload[field])
    except Exception:
        raise VitalValidationError(f"Field '{field}' must be an integer")


def _require_float(payload: Dict[str, Any], field: str) -> float:
    if field not in payload:
        raise VitalValidationError(f"Missing required field '{field}'")
    try:
        return float(payload[field])
    except Exception:
        raise VitalValidationError(f"Field '{field}' must be a number")


def validate_event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize an incoming vital event payload.

    Returns normalized_payload (units normalized).
    """
    if event_type not in ("heart_rate", "blood_pressure", "glucose", "temperature"):
        raise VitalValidationError(
            f"Unsupported event_type '{event_type}'. Supported: heart_rate, blood_pressure, glucose, temperature"
        )
    if not payload:
        raise VitalValidationError("Payload must not be empty")

    if event_type == "heart_rate":
        bpm = _require_int(payload, "bpm")
        norm: Dict[str, Any] = {"bpm": bpm}
        if "quality" in payload and payload["quality"] is not None:
            norm["quality"] = str(payload["quality"])
        return norm

    if event_type == "blood_pressure":
        sys = _require_int(payload, "sys")
        dia = _require_int(payload, "dia")
        norm = {"sys": sys, "dia": dia}
        if "pulse" in payload and payload["pulse"] is not None:
            try:
                norm["pulse"] = int(payload["pulse"])
            except Exception:
                raise VitalValidationError("Field 'pulse' must be an integer when provided")
        return norm

    if event_type == "glucose":
        # Support either mg/dL or mmol/L, normalize to mg/dL
        if "mg_dl" in payload and payload["mg_dl"] is not None:
            mg_dl = float(payload["mg_dl"])
        elif "mmol_l" in payload and payload["mmol_l"] is not None:
            mmol = float(payload["mmol_l"])
            mg_dl = mmol * 18.0
        else:
            raise VitalValidationError("Glucose payload must include either 'mg_dl' or 'mmol_l'")
        return {"glucose_mg_dl": float(mg_dl)}

    # temperature
    if "c" in payload and payload["c"] is not None:
        c = float(payload["c"])
    elif "f" in payload and payload["f"] is not None:
        f = float(payload["f"])
        c = (f - 32.0) * (5.0 / 9.0)
    else:
        raise VitalValidationError("Temperature payload must include either 'c' or 'f'")
    return {"temperature_c": float(c)}


def map_to_memory_facts(
    user_id: int,
    event_type: SupportedVital,
    normalized_payload: Dict[str, Any],
    device_id: Optional[str],
    recorded_at: Optional[datetime],
) -> List[MemoryUpdate]:
    """
    Map normalized vitals payload to one or more memory updates.

    Keep heart_rate behavior compatible with C1: store a dict including bpm + recorded_at + device_id.
    For new vitals, store a dict with value+unit+recorded_at+device_id for consistency.
    """
    ts = recorded_at.isoformat() if recorded_at else None
    updates: List[MemoryUpdate] = []

    if event_type == "heart_rate":
        value: Dict[str, Any] = {
            "bpm": float(normalized_payload["bpm"]),
            "recorded_at": ts,
            "device_id": device_id,
        }
        if "quality" in normalized_payload:
            value["quality"] = normalized_payload["quality"]
        updates.append(MemoryUpdate(domain="vitals", key="heart_rate_bpm", value=value))
        return updates

    if event_type == "blood_pressure":
        updates.append(
            MemoryUpdate(
                domain="vitals",
                key="blood_pressure_sys",
                value={"value": int(normalized_payload["sys"]), "unit": "mmHg", "recorded_at": ts, "device_id": device_id},
            )
        )
        updates.append(
            MemoryUpdate(
                domain="vitals",
                key="blood_pressure_dia",
                value={"value": int(normalized_payload["dia"]), "unit": "mmHg", "recorded_at": ts, "device_id": device_id},
            )
        )
        if "pulse" in normalized_payload:
            # Optional: also set heart_rate_bpm using pulse
            value_hr = {"bpm": float(normalized_payload["pulse"]), "recorded_at": ts, "device_id": device_id}
            updates.append(MemoryUpdate(domain="vitals", key="heart_rate_bpm", value=value_hr))
        return updates

    if event_type == "glucose":
        updates.append(
            MemoryUpdate(
                domain="vitals",
                key="glucose_mg_dl",
                value={
                    "value": float(normalized_payload["glucose_mg_dl"]),
                    "unit": "mg/dL",
                    "recorded_at": ts,
                    "device_id": device_id,
                },
            )
        )
        return updates

    # temperature
    updates.append(
        MemoryUpdate(
            domain="vitals",
            key="temperature_c",
            value={
                "value": float(normalized_payload["temperature_c"]),
                "unit": "C",
                "recorded_at": ts,
                "device_id": device_id,
            },
        )
    )
    return updates


def build_dedupe_key(
    user_id: int,
    event_type: SupportedVital,
    recorded_at: Optional[datetime],
    received_at: Optional[datetime],
    device_id: Optional[str] = None,
) -> str:
    """
    Build dedupe key using existing 5-minute bucketing method.
    Format is deterministic and includes event_type (already in prefix).
    """
    return _build_dedupe_key_5m(event_type=event_type, user_id=user_id, recorded_at=recorded_at, received_at=received_at)

