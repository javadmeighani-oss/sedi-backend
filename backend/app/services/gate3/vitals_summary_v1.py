"""Stable V1 vitals summary contract — additive, backward compatible."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate5.gadget_hub_status import build_hub_status_payload

MONITORING_STATES = frozenset({"active", "recent", "stale", "disconnected", "no_data", "unknown"})
CANONICAL_VITAL_KEYS = (
    "heart_rate",
    "spo2",
    "temperature",
    "blood_pressure",
    "respiratory_rate",
    "ecg",
)


def _freshness_thresholds() -> Dict[str, int]:
  return {
      "active_minutes": int(os.getenv("SEDI_VITALS_ACTIVE_MINUTES", "5")),
      "recent_minutes": int(os.getenv("SEDI_VITALS_RECENT_MINUTES", "30")),
      "stale_minutes": int(os.getenv("SEDI_VITALS_STALE_MINUTES", "120")),
  }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _freshness_state(recorded_at: Optional[datetime], thresholds: Dict[str, int]) -> str:
    if recorded_at is None:
        return "unknown"
    age = _utc_now() - recorded_at
    mins = age.total_seconds() / 60.0
    if mins <= thresholds["active_minutes"]:
        return "active"
    if mins <= thresholds["recent_minutes"]:
        return "recent"
    if mins <= thresholds["stale_minutes"]:
        return "stale"
    return "stale"


def _vital_object(
    value: Any,
    *,
    unit: str,
    recorded_at: Optional[str],
    received_at: Optional[str],
    source: str,
    source_device_id: Optional[str] = None,
    quality: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value == 0 and unit not in {"bpm", "percent_c", "percent"}:
        pass
    thresholds = _freshness_thresholds()
    rec_dt = _parse_dt(recorded_at) or _parse_dt(received_at)
    obj: Dict[str, Any] = {
        "value": value,
        "unit": unit,
        "recorded_at": recorded_at,
        "received_at": received_at,
        "source": source,
        "freshness": _freshness_state(rec_dt, thresholds),
    }
    if source_device_id:
        obj["source_device_id"] = source_device_id
    if quality:
        obj["quality"] = quality
    if extra:
        obj.update(extra)
    return obj


def _blood_pressure_object(
    bp: Any,
    *,
    recorded_at: Optional[str],
    received_at: Optional[str],
    source: str,
    source_device_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(bp, dict):
        return None
    systolic = bp.get("systolic")
    diastolic = bp.get("diastolic")
    if systolic is None and diastolic is None:
        return None
    thresholds = _freshness_thresholds()
    rec_dt = _parse_dt(recorded_at) or _parse_dt(received_at)
    obj: Dict[str, Any] = {
        "systolic": systolic,
        "diastolic": diastolic,
        "unit": "mmHg",
        "recorded_at": recorded_at,
        "received_at": received_at,
        "source": source,
        "freshness": _freshness_state(rec_dt, thresholds),
    }
    if source_device_id:
        obj["source_device_id"] = source_device_id
    return obj


def _ecg_object(
    ecg: Any,
    *,
    recorded_at: Optional[str],
    received_at: Optional[str],
    source: str,
    source_device_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if ecg is None:
        return None
    thresholds = _freshness_thresholds()
    rec_dt = _parse_dt(recorded_at) or _parse_dt(received_at)
    obj: Dict[str, Any] = {
        "monitoring_available": bool(ecg),
        "signal_available": bool(ecg),
        "recorded_at": recorded_at,
        "received_at": received_at,
        "source": source,
        "freshness": _freshness_state(rec_dt, thresholds),
    }
    if source_device_id:
        obj["source_device_id"] = source_device_id
    return obj


def _parse_device_payload(payload_json: Optional[str]) -> Dict[str, Any]:
    if not payload_json:
        return {}
    try:
        data = json.loads(payload_json)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


_REGISTERED_HUB_DISCONNECT_STATUSES = frozenset({"disconnected", "revoked"})


def _compute_monitoring_state(
    hub_status: Dict[str, Any],
    latest_received_at: Optional[datetime],
    thresholds: Dict[str, int],
) -> str:
    if latest_received_at is not None:
        return _freshness_state(latest_received_at, thresholds)

    hub = hub_status.get("status")
    has_hub = bool(hub_status.get("has_hub"))
    if not has_hub or hub == "not_registered":
        return "no_data"
    if hub in _REGISTERED_HUB_DISCONNECT_STATUSES:
        return "disconnected"
    return "no_data"


def build_vitals_summary_v1(db: Session, user_id: int) -> Dict[str, Any]:
    """Build stable V1 vitals response with legacy keys preserved."""
    thresholds = _freshness_thresholds()
    out: Dict[str, Any] = {"sources": [], "vitals_v1": {}}

    latest_health = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == user_id)
        .order_by(models.HealthData.created_at.desc())
        .first()
    )
    legacy_health: Dict[str, Any] = {}
    if latest_health:
        rec = latest_health.created_at.isoformat() + "Z" if latest_health.created_at else None
        legacy_health = {
            "heart_rate": latest_health.heart_rate,
            "temperature": latest_health.temperature,
            "spo2": latest_health.spo2,
            "recorded_at": rec,
        }
        out["legacy_health"] = legacy_health
        out["sources"].append("health_data")

    latest_device = (
        db.query(models.DeviceEvent)
        .filter(models.DeviceEvent.user_id == user_id)
        .order_by(models.DeviceEvent.received_at.desc())
        .first()
    )
    device_payload: Dict[str, Any] = {}
    device_rec_at: Optional[str] = None
    device_recv_at: Optional[str] = None
    if latest_device:
        device_rec_at = (
            latest_device.recorded_at.isoformat() + "Z" if latest_device.recorded_at else None
        )
        device_recv_at = (
            latest_device.received_at.isoformat() + "Z" if latest_device.received_at else None
        )
        out["device_event"] = {
            "event_type": latest_device.event_type,
            "payload": latest_device.payload_json,
            "received_at": device_recv_at,
        }
        out["sources"].append("device_events")
        device_payload = _parse_device_payload(latest_device.payload_json)

    hub_status = build_hub_status_payload(db, user_id)
    latest_dt = _parse_dt(device_recv_at) or _parse_dt(legacy_health.get("recorded_at"))
    monitoring_state = _compute_monitoring_state(hub_status, latest_dt, thresholds)

    hr = device_payload.get("heart_rate") or legacy_health.get("heart_rate")
    spo2 = device_payload.get("spo2") or legacy_health.get("spo2")
    temp = device_payload.get("temperature") or legacy_health.get("temperature")
    bp = device_payload.get("blood_pressure")
    rr = device_payload.get("respiratory_rate")
    ecg = device_payload.get("ecg")

    src = "device_events" if device_payload else ("health_data" if legacy_health else "none")
    rec = device_rec_at or legacy_health.get("recorded_at")
    recv = device_recv_at or legacy_health.get("recorded_at")
    dev_id = latest_device.device_id if latest_device else None

    vitals: Dict[str, Any] = {
        "heart_rate": _vital_object(
            hr, unit="bpm", recorded_at=rec, received_at=recv, source=src, source_device_id=dev_id
        ),
        "spo2": _vital_object(
            spo2, unit="percent", recorded_at=rec, received_at=recv, source=src, source_device_id=dev_id
        ),
        "temperature": _vital_object(
            temp, unit="celsius", recorded_at=rec, received_at=recv, source=src, source_device_id=dev_id
        ),
        "blood_pressure": _blood_pressure_object(
            bp,
            recorded_at=rec,
            received_at=recv,
            source=src,
            source_device_id=dev_id,
        ),
        "respiratory_rate": _vital_object(
            rr, unit="breaths_per_min", recorded_at=rec, received_at=recv, source=src, source_device_id=dev_id
        ),
        "ecg": _ecg_object(
            ecg,
            recorded_at=rec,
            received_at=recv,
            source=src,
            source_device_id=dev_id,
        ),
    }
    for key in CANONICAL_VITAL_KEYS:
        vitals.setdefault(key, None)

    out["vitals_v1"] = {
        "monitoring_state": monitoring_state,
        "vitals": vitals,
        "hub_status": hub_status.get("status"),
    }
    return out
