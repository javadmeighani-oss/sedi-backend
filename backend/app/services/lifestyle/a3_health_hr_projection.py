"""A3 Lifestyle SELF HR presentation — I9 + measurement/rollup reuse. Schema-free."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.self_producer_adapter import resolve_or_ensure_self_health_subject_id
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
    status = "INSUFFICIENT_DATA"
    if subject_id is not None:
        result = evaluate_canonical_hr_stability(db, health_subject_id=int(subject_id))
        status = result.status.value

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
            }
        )

    available_from = points[0]["bucket_start"] if points else latest_at
    available_to = points[-1]["bucket_start"] if points else latest_at

    return {
        "hr_status": status,
        "latest_value": latest_value,
        "latest_received_at": latest_at,
        "range_key": key,
        "history_bucket_kind": bucket_kind,
        "history": points,
        "available_from": available_from,
        "available_to": available_to,
        "requested_days": days,
    }
