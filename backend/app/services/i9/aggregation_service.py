"""Governed health-subject physiological aggregation with weighted rollups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.time_buckets import BucketKind, bucket_bounds, iter_bucket_starts


@dataclass
class BucketStats:
    sample_count: int
    sum_value: float
    min_value: Optional[float]
    max_value: Optional[float]
    avg_value: Optional[float]
    arrhythmia_event_count: int
    critical_event_count: int

    @classmethod
    def empty(cls) -> "BucketStats":
        return cls(0, 0.0, None, None, None, 0, 0)

    @classmethod
    def from_measurements(cls, values: List[float]) -> "BucketStats":
        if not values:
            return cls.empty()
        return cls(
            sample_count=len(values),
            sum_value=float(sum(values)),
            min_value=float(min(values)),
            max_value=float(max(values)),
            avg_value=float(sum(values)) / len(values),
            arrhythmia_event_count=0,
            critical_event_count=0,
        )

    def merge_weighted(self, other: "BucketStats") -> "BucketStats":
        if other.sample_count == 0:
            return self
        if self.sample_count == 0:
            return other
        total_n = self.sample_count + other.sample_count
        total_sum = self.sum_value + other.sum_value
        return BucketStats(
            sample_count=total_n,
            sum_value=total_sum,
            min_value=min(v for v in (self.min_value, other.min_value) if v is not None),
            max_value=max(v for v in (self.max_value, other.max_value) if v is not None),
            avg_value=total_sum / total_n,
            arrhythmia_event_count=self.arrhythmia_event_count + other.arrhythmia_event_count,
            critical_event_count=self.critical_event_count + other.critical_event_count,
        )


def _rollup_storage_user_id(subject: models.HealthSubject) -> Optional[int]:
    """Legacy user_id compatibility when subject has linked account."""
    return subject.linked_user_id


def _technically_valid_pm_filter(q):
    """Only exclude measurements rejected by existing ingestion contract."""
    return q.filter(models.PhysiologicalMeasurement.ingestion_status == "accepted")


def compute_bucket_stats_from_measurements(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str,
    bucket_start: datetime,
    bucket_end: datetime,
) -> BucketStats:
    rows = (
        _technically_valid_pm_filter(
            db.query(models.PhysiologicalMeasurement.numeric_value).filter(
                models.PhysiologicalMeasurement.health_subject_id == health_subject_id,
                models.PhysiologicalMeasurement.measurement_type == measurement_type,
                models.PhysiologicalMeasurement.measured_at >= bucket_start,
                models.PhysiologicalMeasurement.measured_at < bucket_end,
            )
        )
        .all()
    )
    stats = BucketStats.from_measurements([float(r[0]) for r in rows])
    events = (
        db.query(models.DeviceReportedCardiacEvent)
        .filter(
            models.DeviceReportedCardiacEvent.health_subject_id == health_subject_id,
            models.DeviceReportedCardiacEvent.detected_at >= bucket_start,
            models.DeviceReportedCardiacEvent.detected_at < bucket_end,
        )
        .all()
    )
    for ev in events:
        stats.arrhythmia_event_count += 1
        if ev.event_code and "critical" in ev.event_code.lower():
            stats.critical_event_count += 1
    return stats


def find_rollup_row(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str,
    bucket_kind: str,
    bucket_start: datetime,
) -> Optional[models.PhysiologicalMeasurementRollup]:
    return (
        db.query(models.PhysiologicalMeasurementRollup)
        .filter(
            models.PhysiologicalMeasurementRollup.health_subject_id == health_subject_id,
            models.PhysiologicalMeasurementRollup.measurement_type == measurement_type,
            models.PhysiologicalMeasurementRollup.bucket_kind == bucket_kind,
            models.PhysiologicalMeasurementRollup.bucket_start == bucket_start,
        )
        .first()
    )


def upsert_rollup(
    db: Session,
    *,
    subject: models.HealthSubject,
    measurement_type: str,
    bucket_kind: str,
    bucket_start: datetime,
    bucket_end: datetime,
    stats: BucketStats,
    commit: bool = True,
) -> Tuple[Optional[models.PhysiologicalMeasurementRollup], bool]:
    """Idempotent subject-native upsert; user_id optional for legacy compatibility."""
    storage_user_id = _rollup_storage_user_id(subject)
    existing = find_rollup_row(
        db,
        health_subject_id=subject.id,
        measurement_type=measurement_type,
        bucket_kind=bucket_kind,
        bucket_start=bucket_start,
    )
    if subject.id is None:
        return existing, False

    coverage = float(stats.sample_count) / max(1.0, float((bucket_end - bucket_start).total_seconds() / 60.0))
    if existing is not None:
        existing.sample_count = stats.sample_count
        existing.avg_value = stats.avg_value
        existing.min_value = stats.min_value
        existing.max_value = stats.max_value
        existing.coverage = coverage
        existing.arrhythmia_event_count = stats.arrhythmia_event_count
        existing.critical_event_count = stats.critical_event_count
        existing.bucket_end = bucket_end
        db.add(existing)
        if commit:
            db.commit()
            db.refresh(existing)
        else:
            db.flush()
        return existing, False

    row = models.PhysiologicalMeasurementRollup(
        user_id=storage_user_id,
        health_subject_id=subject.id,
        measurement_type=measurement_type,
        bucket_kind=bucket_kind,
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        sample_count=stats.sample_count,
        avg_value=stats.avg_value,
        min_value=stats.min_value,
        max_value=stats.max_value,
        coverage=coverage,
        arrhythmia_event_count=stats.arrhythmia_event_count,
        critical_event_count=stats.critical_event_count,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row, True


def rebuild_daily_bucket(
    db: Session,
    *,
    subject: models.HealthSubject,
    measurement_type: str,
    ref: datetime,
    preferred_language: Optional[str] = None,
    commit: bool = True,
) -> BucketStats:
    b_start, b_end = bucket_bounds("daily", ref=ref, preferred_language=preferred_language)
    stats = compute_bucket_stats_from_measurements(
        db,
        health_subject_id=subject.id,
        measurement_type=measurement_type,
        bucket_start=b_start,
        bucket_end=b_end,
    )
    upsert_rollup(
        db,
        subject=subject,
        measurement_type=measurement_type,
        bucket_kind="daily",
        bucket_start=b_start,
        bucket_end=b_end,
        stats=stats,
        commit=commit,
    )
    return stats


def rebuild_higher_bucket_from_daily_rollups(
    db: Session,
    *,
    subject: models.HealthSubject,
    measurement_type: str,
    bucket_kind: BucketKind,
    ref: datetime,
    preferred_language: Optional[str] = None,
    commit: bool = True,
) -> BucketStats:
    """Weighted rollup from daily child buckets (never unweighted mean of averages)."""
    if bucket_kind not in ("weekly", "calendar_month", "yearly"):
        raise ValueError("INVALID_HIGHER_BUCKET")
    b_start, b_end = bucket_bounds(bucket_kind, ref=ref, preferred_language=preferred_language)
    dailies = (
        db.query(models.PhysiologicalMeasurementRollup)
        .filter(
            models.PhysiologicalMeasurementRollup.health_subject_id == subject.id,
            models.PhysiologicalMeasurementRollup.measurement_type == measurement_type,
            models.PhysiologicalMeasurementRollup.bucket_kind == "daily",
            models.PhysiologicalMeasurementRollup.bucket_start >= b_start,
            models.PhysiologicalMeasurementRollup.bucket_start < b_end,
        )
        .all()
    )
    if dailies:
        merged = BucketStats.empty()
        for d in dailies:
            if d.sample_count and d.avg_value is not None:
                child = BucketStats(
                    sample_count=int(d.sample_count),
                    sum_value=float(d.avg_value) * int(d.sample_count),
                    min_value=d.min_value,
                    max_value=d.max_value,
                    avg_value=d.avg_value,
                    arrhythmia_event_count=int(d.arrhythmia_event_count or 0),
                    critical_event_count=int(d.critical_event_count or 0),
                )
                merged = merged.merge_weighted(child)
    else:
        merged = compute_bucket_stats_from_measurements(
            db,
            health_subject_id=subject.id,
            measurement_type=measurement_type,
            bucket_start=b_start,
            bucket_end=b_end,
        )
    upsert_rollup(
        db,
        subject=subject,
        measurement_type=measurement_type,
        bucket_kind=bucket_kind,
        bucket_start=b_start,
        bucket_end=b_end,
        stats=merged,
        commit=commit,
    )
    return merged


def compute_aggregate_for_range(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str,
    bucket_kind: BucketKind,
    range_start: datetime,
    range_end: datetime,
    preferred_language: Optional[str] = None,
) -> List[dict]:
    """Compute or load aggregates for each bucket in range (on-demand read path)."""
    require_subject = (
        db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    )
    if require_subject is None:
        return []
    out: List[dict] = []
    for b_start, b_end in iter_bucket_starts(
        bucket_kind, range_start=range_start, range_end=range_end, preferred_language=preferred_language
    ):
        row = find_rollup_row(
            db,
            health_subject_id=health_subject_id,
            measurement_type=measurement_type,
            bucket_kind=bucket_kind,
            bucket_start=b_start,
        )
        if row is not None:
            stats = BucketStats(
                sample_count=int(row.sample_count),
                sum_value=float(row.avg_value or 0) * int(row.sample_count),
                min_value=row.min_value,
                max_value=row.max_value,
                avg_value=row.avg_value,
                arrhythmia_event_count=int(row.arrhythmia_event_count or 0),
                critical_event_count=int(row.critical_event_count or 0),
            )
        else:
            stats = compute_bucket_stats_from_measurements(
                db,
                health_subject_id=health_subject_id,
                measurement_type=measurement_type,
                bucket_start=b_start,
                bucket_end=b_end,
            )
        out.append(
            {
                "bucket_kind": bucket_kind,
                "bucket_start": b_start,
                "bucket_end": b_end,
                "sample_count": stats.sample_count,
                "avg_value": stats.avg_value,
                "min_value": stats.min_value,
                "max_value": stats.max_value,
                "arrhythmia_event_count": stats.arrhythmia_event_count,
                "critical_event_count": stats.critical_event_count,
            }
        )
    return out
