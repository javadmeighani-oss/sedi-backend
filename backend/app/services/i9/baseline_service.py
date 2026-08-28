"""Personal Observed Baseline V1 — deterministic median-of-daily-medians + MAD."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.health_subject_service import preferred_language_for_subject
from backend.app.services.i9.time_buckets import bucket_bounds, iter_bucket_starts

BASELINE_METHOD = "PERSONAL_OBSERVED_BASELINE_V1"
BASELINE_VERSION = 1
BASELINE_SCOPE_V1 = "heart_rate"
ROLLING_WINDOW_DAYS = 28
MIN_VALID_DAYS_TO_CREATE = 7
MIN_ESTABLISHED_DAYS = 14


@dataclass
class BaselineComputation:
    status: str  # NONE | PROVISIONAL | ESTABLISHED
    baseline_value: Optional[float]
    dispersion_value: Optional[float]
    valid_day_count: int
    coverage: float
    window_start: datetime
    window_end: datetime
    daily_medians: List[float]


def _median(values: List[float]) -> float:
    return float(statistics.median(values))


def _mad_over_series(series: List[float], center: float) -> float:
    return _median([abs(v - center) for v in series])


def _accepted_measurements_query(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str,
    bucket_start: datetime,
    bucket_end: datetime,
):
    return (
        db.query(models.PhysiologicalMeasurement.numeric_value)
        .filter(
            models.PhysiologicalMeasurement.health_subject_id == health_subject_id,
            models.PhysiologicalMeasurement.measurement_type == measurement_type,
            models.PhysiologicalMeasurement.ingestion_status == "accepted",
            models.PhysiologicalMeasurement.measured_at >= bucket_start,
            models.PhysiologicalMeasurement.measured_at < bucket_end,
        )
        .all()
    )


def compute_personal_observed_baseline(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str = BASELINE_SCOPE_V1,
    ref: Optional[datetime] = None,
    preferred_language: Optional[str] = None,
) -> BaselineComputation:
    if measurement_type != BASELINE_SCOPE_V1:
        raise ValueError("BASELINE_SCOPE_V1_HEART_RATE_ONLY")
    ref = ref or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    last_start, last_end = bucket_bounds("daily", ref=ref, preferred_language=preferred_language)
    window_end = last_end
    window_start = last_start - timedelta(days=ROLLING_WINDOW_DAYS - 1)

    daily_medians: List[float] = []
    for b_start, b_end in iter_bucket_starts(
        "daily",
        range_start=window_start,
        range_end=window_end,
        preferred_language=preferred_language,
    ):
        rows = _accepted_measurements_query(
            db,
            health_subject_id=health_subject_id,
            measurement_type=measurement_type,
            bucket_start=b_start,
            bucket_end=b_end,
        )
        if not rows:
            continue
        values = [float(r[0]) for r in rows]
        daily_medians.append(_median(values))

    valid_day_count = len(daily_medians)
    coverage = valid_day_count / float(ROLLING_WINDOW_DAYS)

    if valid_day_count < MIN_VALID_DAYS_TO_CREATE:
        return BaselineComputation(
            status="NONE",
            baseline_value=None,
            dispersion_value=None,
            valid_day_count=valid_day_count,
            coverage=coverage,
            window_start=window_start,
            window_end=window_end,
            daily_medians=daily_medians,
        )

    center = _median(daily_medians)
    dispersion = _mad_over_series(daily_medians, center)
    status = "ESTABLISHED" if valid_day_count >= MIN_ESTABLISHED_DAYS else "PROVISIONAL"
    return BaselineComputation(
        status=status,
        baseline_value=center,
        dispersion_value=dispersion,
        valid_day_count=valid_day_count,
        coverage=coverage,
        window_start=window_start,
        window_end=window_end,
        daily_medians=daily_medians,
    )


def find_baseline_row(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str,
    window_start: datetime,
) -> Optional[models.PhysiologicalBaseline]:
    return (
        db.query(models.PhysiologicalBaseline)
        .filter(
            models.PhysiologicalBaseline.health_subject_id == health_subject_id,
            models.PhysiologicalBaseline.measurement_type == measurement_type,
            models.PhysiologicalBaseline.baseline_version == BASELINE_VERSION,
            models.PhysiologicalBaseline.window_start == window_start,
        )
        .first()
    )


def upsert_personal_observed_baseline(
    db: Session,
    *,
    subject: models.HealthSubject,
    ref: Optional[datetime] = None,
    commit: bool = True,
) -> Optional[models.PhysiologicalBaseline]:
    lang = preferred_language_for_subject(db, subject)
    computed = compute_personal_observed_baseline(
        db,
        health_subject_id=subject.id,
        ref=ref,
        preferred_language=lang,
    )
    existing = find_baseline_row(
        db,
        health_subject_id=subject.id,
        measurement_type=BASELINE_SCOPE_V1,
        window_start=computed.window_start,
    )
    if computed.status == "NONE":
        if existing is not None:
            db.delete(existing)
            if commit:
                db.commit()
            else:
                db.flush()
        return None

    now = datetime.now(timezone.utc)
    source_range = json.dumps(
        {
            "rolling_window_days": ROLLING_WINDOW_DAYS,
            "valid_day_count": computed.valid_day_count,
            "daily_medians": computed.daily_medians,
            "disclaimer": "descriptive_personal_history_not_diagnosis",
        },
        sort_keys=True,
    )
    fields = dict(
        user_id=subject.linked_user_id,
        health_subject_id=subject.id,
        measurement_type=BASELINE_SCOPE_V1,
        window_start=computed.window_start,
        window_end=computed.window_end,
        coverage=computed.coverage,
        quality=computed.status,
        baseline_version=BASELINE_VERSION,
        derived_at=now,
        source_range=source_range,
        baseline_value=computed.baseline_value,
        baseline_method=BASELINE_METHOD,
        dispersion_value=computed.dispersion_value,
        valid_day_count=computed.valid_day_count,
    )
    if existing is not None:
        for k, v in fields.items():
            setattr(existing, k, v)
        row = existing
    else:
        row = models.PhysiologicalBaseline(**fields)
        db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def rebuild_subject_vitals_internal(
    db: Session,
    *,
    subject: models.HealthSubject,
    ref: Optional[datetime] = None,
    commit: bool = True,
) -> dict:
    """Backend-owned rebuild: daily rollup + personal observed baseline."""
    from backend.app.services.i9.aggregation_service import rebuild_daily_bucket

    lang = preferred_language_for_subject(db, subject)
    ref = ref or datetime.now(timezone.utc)
    rebuild_daily_bucket(
        db,
        subject=subject,
        measurement_type=BASELINE_SCOPE_V1,
        ref=ref,
        preferred_language=lang,
        commit=False,
    )
    baseline = upsert_personal_observed_baseline(db, subject=subject, ref=ref, commit=False)
    if commit:
        db.commit()
    return {"baseline_id": baseline.id if baseline else None, "status": baseline.quality if baseline else "NONE"}
