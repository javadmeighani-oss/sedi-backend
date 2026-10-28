"""A3 Lifestyle SELF HR presentation — I9 measurement/rollup + DEVICE_REPORTED status.

BPM/history = observed vitals only.
hr_status = gadget DEVICE_REPORTED STABLE|UNSTABLE when present; never MAD-relabeled.
hr_stability_compact = legacy MAD compact (non-authoritative for Frontend device path).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.self_producer_adapter import resolve_or_ensure_self_health_subject_id
from backend.app.services.i9.device_reported_vital_status import (
    SOURCE_CLASS as DEVICE_REPORTED_SOURCE,
    get_effective_device_reported_vital_status,
)
from backend.app.services.i9.hr_stability import evaluate_canonical_hr_stability

_RANGE_DAYS = {
    "7d": 7,
    "30d": 30,
    "3m": 90,
    "1y": 365,
}


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _summary(points: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Sample-weighted average and the lowest / highest reading over the range (None without data)."""
    if not points:
        return None
    weight = sum(max(1, int(p.get("count") or 0)) for p in points)
    avg = sum(float(p["avg"]) * max(1, int(p.get("count") or 0)) for p in points) / weight
    lows = [p["min"] for p in points if p.get("min") is not None]
    highs = [p["max"] for p in points if p.get("max") is not None]
    return {
        "avg": round(avg),
        "min": round(min(lows)) if lows else round(min(float(p["avg"]) for p in points)),
        "max": round(max(highs)) if highs else round(max(float(p["avg"]) for p in points)),
    }


def _trend(points: list[dict[str, Any]]) -> str:
    """'steady' | 'up' | 'down' | 'insufficient' - the first quarter against the last quarter of the range. A plain
    observation of the user's own numbers, never a clinical reading."""
    if len(points) < 4:
        return "insufficient"
    q = max(1, len(points) // 4)
    first = sum(float(p["avg"]) for p in points[:q]) / q
    last = sum(float(p["avg"]) for p in points[-q:]) / q
    if last - first >= 5:
        return "up"
    if first - last >= 5:
        return "down"
    return "steady"


def _data_status(db: Session, user_id: int, now: datetime, latest_at: Optional[str]) -> dict[str, Any]:
    """Exact state of the gadget's data: receiving / quiet / stale / never, today's count and gaps, this week's coverage."""
    from backend.app.services.i7.memory_explorer import _zone, day_bounds_utc

    pm = models.PhysiologicalMeasurement
    zone, _ = _zone(db, user_id)
    today = now.astimezone(zone).date()
    start, end = day_bounds_utc(today, zone)
    times = [
        _as_utc(t)
        for (t,) in db.query(pm.measured_at)
        .filter(
            pm.user_id == user_id,
            pm.measurement_type == "heart_rate",
            pm.ingestion_status == "accepted",
            pm.measured_at >= start,
            pm.measured_at < end,
        )
        .order_by(pm.measured_at.asc())
        .limit(5000)
        .all()
        if t is not None
    ]
    last_dt = _as_utc(datetime.fromisoformat(latest_at)) if latest_at else None
    minutes_since = int((now - last_dt).total_seconds() // 60) if last_dt else None
    if last_dt is None:
        state = "never"
    elif minutes_since <= 30:
        state = "receiving"
    elif minutes_since <= 24 * 60:
        state = "quiet"
    else:
        state = "stale"
    longest_gap = 0
    marks = [start] + times + [min(now, end)] if times else []
    for a, b in zip(marks, marks[1:]):
        longest_gap = max(longest_gap, int((b - a).total_seconds() // 60))
    # coverage of the last 7 local days from the daily rollups
    since = now - timedelta(days=7)
    rollups = (
        db.query(models.PhysiologicalMeasurementRollup.sample_count)
        .filter(
            models.PhysiologicalMeasurementRollup.user_id == user_id,
            models.PhysiologicalMeasurementRollup.measurement_type == "heart_rate",
            models.PhysiologicalMeasurementRollup.bucket_kind == "daily",
            models.PhysiologicalMeasurementRollup.bucket_start >= since,
        )
        .all()
    )
    days_with = [int(c or 0) for (c,) in rollups if (c or 0) > 0]
    return {
        "state": state,
        "minutes_since_last": minutes_since,
        "today": {
            "count": len(times),
            "first_at": times[0].astimezone(zone).strftime("%H:%M") if times else None,
            "last_at": times[-1].astimezone(zone).strftime("%H:%M") if times else None,
            "longest_gap_minutes": longest_gap if times else None,
        },
        "week": {
            "days_with_data": len(days_with),
            "avg_per_day": round(sum(days_with) / len(days_with)) if days_with else 0,
        },
    }


def build_lifestyle_hr_projection(
    db: Session, user_id: int, *, range_key: str = "7d"
) -> dict[str, Any]:
    """JWT SELF-only compact HR presentation. No clinical inference. No subject IDs."""
    key = (range_key or "7d").lower()
    if key not in _RANGE_DAYS:
        key = "7d"
    days = _RANGE_DAYS[key]
    now = datetime.now(timezone.utc)

    subject_id = resolve_or_ensure_self_health_subject_id(db, int(user_id))

    # Authoritative gadget status only — never map MAD into DEVICE_REPORTED.
    hr_status: Optional[str] = None
    hr_status_source: Optional[str] = None
    hr_status_observed_at: Optional[str] = None
    if subject_id is not None:
        device_eff = get_effective_device_reported_vital_status(
            db, health_subject_id=int(subject_id)
        )
        if device_eff is not None and device_eff.status in ("STABLE", "UNSTABLE"):
            hr_status = str(device_eff.status)
            hr_status_source = DEVICE_REPORTED_SOURCE
            ts = _as_utc(device_eff.detected_at)
            hr_status_observed_at = ts.isoformat() if ts else None

    # Legacy MAD compact — distinguishable; not device-reported authority.
    hr_stability_compact = "INSUFFICIENT_DATA"
    if subject_id is not None:
        result = evaluate_canonical_hr_stability(
            db, health_subject_id=int(subject_id)
        )
        hr_stability_compact = result.status.value

    latest = (
        db.query(models.PhysiologicalMeasurement)
        .filter(
            models.PhysiologicalMeasurement.user_id == int(user_id),
            models.PhysiologicalMeasurement.measurement_type == "heart_rate",
            models.PhysiologicalMeasurement.ingestion_status == "accepted",
        )
        .order_by(models.PhysiologicalMeasurement.measured_at.desc())
        .first()
    )
    latest_value: Optional[float] = None
    latest_at: Optional[str] = None
    if latest is not None and latest.numeric_value is not None:
        latest_value = float(latest.numeric_value)
        ts = _as_utc(latest.received_at or latest.measured_at)
        latest_at = ts.isoformat() if ts else None

    range_start = now - timedelta(days=days)
    # Prefer daily rollups; fall back to weekly for long ranges when daily sparse.
    bucket_kind = "daily" if days <= 90 else "weekly"
    q = db.query(models.PhysiologicalMeasurementRollup).filter(
        models.PhysiologicalMeasurementRollup.user_id == int(user_id),
        models.PhysiologicalMeasurementRollup.measurement_type == "heart_rate",
        models.PhysiologicalMeasurementRollup.bucket_kind == bucket_kind,
        models.PhysiologicalMeasurementRollup.bucket_start >= range_start,
        models.PhysiologicalMeasurementRollup.bucket_start <= now,
    )
    if subject_id is not None:
        q = q.filter(
            (models.PhysiologicalMeasurementRollup.health_subject_id == int(subject_id))
            | (models.PhysiologicalMeasurementRollup.health_subject_id.is_(None))
        )
    rows = q.order_by(models.PhysiologicalMeasurementRollup.bucket_start.asc()).all()

    points: list[dict[str, Any]] = []
    for r in rows:
        if r.avg_value is None:
            continue
        bs = _as_utc(r.bucket_start)
        points.append(
            {
                "bucket_start": bs.isoformat() if bs else None,
                "avg": float(r.avg_value),
                "min": float(r.min_value) if r.min_value is not None else None,
                "max": float(r.max_value) if r.max_value is not None else None,
                "count": int(r.sample_count or 0),
            }
        )

    available_from = points[0]["bucket_start"] if points else latest_at
    available_to = points[-1]["bucket_start"] if points else latest_at

    return {
        "summary": _summary(points),
        "trend": _trend(points),
        "data_status": _data_status(db, int(user_id), now, latest_at),
        "hr_status": hr_status,
        "hr_status_source": hr_status_source,
        "hr_status_observed_at": hr_status_observed_at,
        "hr_stability_compact": hr_stability_compact,
        "latest_value": latest_value,
        "latest_received_at": latest_at,
        "range_key": key,
        "history_bucket_kind": bucket_kind,
        "history": points,
        "available_from": available_from,
        "available_to": available_to,
        "requested_days": days,
    }
