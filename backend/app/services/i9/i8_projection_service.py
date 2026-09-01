"""I9-owned bounded physiological context projection for I8 (read-only, persisted rollup/baseline only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

V1_MEASUREMENT_TYPE = "heart_rate"
BASELINE_METHOD = "PERSONAL_OBSERVED_BASELINE_V1"
MAX_ROLLUP_ROWS = 2  # daily + weekly
MAX_BASELINE_ROWS = 1


@dataclass(frozen=True)
class I9RollupContextEntry:
    health_subject_id: int
    measurement_type: str
    rollup_id: int
    bucket_kind: str
    bucket_start: datetime
    bucket_end: datetime
    avg_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    sample_count: int
    coverage: Optional[float]


@dataclass(frozen=True)
class I9BaselineContextEntry:
    health_subject_id: int
    measurement_type: str
    baseline_id: int
    baseline_method: str
    baseline_value: Optional[float]
    dispersion_value: Optional[float]
    valid_day_count: Optional[int]
    window_start: datetime
    window_end: datetime
    coverage: Optional[float]
    quality: Optional[str]


@dataclass(frozen=True)
class I8GovernedPhysiologicalContext:
    health_subject_id: Optional[int]
    measurement_type: str
    daily_rollup: Optional[I9RollupContextEntry] = None
    weekly_rollup: Optional[I9RollupContextEntry] = None
    personal_observed_baseline: Optional[I9BaselineContextEntry] = None


def _resolve_self_linked_subject_for_account(
    db: Session,
    account_user_id: int,
) -> Optional[models.HealthSubject]:
    """Fail-closed: exactly one active SELF subject linked to the account."""
    rows = (
        db.query(models.HealthSubject)
        .join(
            models.AccountHealthSubjectAccess,
            models.AccountHealthSubjectAccess.health_subject_id == models.HealthSubject.id,
        )
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.access_role == "SELF",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
            models.HealthSubject.linked_user_id == account_user_id,
            models.HealthSubject.status == "active",
        )
        .all()
    )
    if len(rows) != 1:
        return None
    return rows[0]


def _rollup_entry(row: models.PhysiologicalMeasurementRollup) -> I9RollupContextEntry:
    return I9RollupContextEntry(
        health_subject_id=int(row.health_subject_id),
        measurement_type=row.measurement_type,
        rollup_id=int(row.id),
        bucket_kind=row.bucket_kind,
        bucket_start=row.bucket_start,
        bucket_end=row.bucket_end,
        avg_value=row.avg_value,
        min_value=row.min_value,
        max_value=row.max_value,
        sample_count=int(row.sample_count or 0),
        coverage=row.coverage,
    )


def _baseline_entry(row: models.PhysiologicalBaseline) -> I9BaselineContextEntry:
    return I9BaselineContextEntry(
        health_subject_id=int(row.health_subject_id),
        measurement_type=row.measurement_type,
        baseline_id=int(row.id),
        baseline_method=row.baseline_method or BASELINE_METHOD,
        baseline_value=row.baseline_value,
        dispersion_value=row.dispersion_value,
        valid_day_count=row.valid_day_count,
        window_start=row.window_start,
        window_end=row.window_end,
        coverage=row.coverage,
        quality=row.quality,
    )


def get_bounded_context_projection_for_subject(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str = V1_MEASUREMENT_TYPE,
) -> I8GovernedPhysiologicalContext:
    """Read persisted rollup/baseline rows for an active HealthSubject (managed or self)."""
    subject = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.id == health_subject_id,
            models.HealthSubject.status == "active",
        )
        .first()
    )
    if subject is None:
        return I8GovernedPhysiologicalContext(
            health_subject_id=None,
            measurement_type=measurement_type,
        )
    return _load_bounded_projection_for_subject_row(db, subject=subject, measurement_type=measurement_type)


def _load_bounded_projection_for_subject_row(
    db: Session,
    *,
    subject: models.HealthSubject,
    measurement_type: str,
) -> I8GovernedPhysiologicalContext:
    daily_row = (
        db.query(models.PhysiologicalMeasurementRollup)
        .filter(
            models.PhysiologicalMeasurementRollup.health_subject_id == subject.id,
            models.PhysiologicalMeasurementRollup.measurement_type == measurement_type,
            models.PhysiologicalMeasurementRollup.bucket_kind == "daily",
        )
        .order_by(models.PhysiologicalMeasurementRollup.bucket_start.desc())
        .limit(1)
        .first()
    )
    weekly_row = (
        db.query(models.PhysiologicalMeasurementRollup)
        .filter(
            models.PhysiologicalMeasurementRollup.health_subject_id == subject.id,
            models.PhysiologicalMeasurementRollup.measurement_type == measurement_type,
            models.PhysiologicalMeasurementRollup.bucket_kind == "weekly",
        )
        .order_by(models.PhysiologicalMeasurementRollup.bucket_start.desc())
        .limit(1)
        .first()
    )
    baseline_row = (
        db.query(models.PhysiologicalBaseline)
        .filter(
            models.PhysiologicalBaseline.health_subject_id == subject.id,
            models.PhysiologicalBaseline.measurement_type == measurement_type,
            models.PhysiologicalBaseline.baseline_method == BASELINE_METHOD,
        )
        .order_by(models.PhysiologicalBaseline.derived_at.desc())
        .limit(1)
        .first()
    )

    return I8GovernedPhysiologicalContext(
        health_subject_id=subject.id,
        measurement_type=measurement_type,
        daily_rollup=_rollup_entry(daily_row) if daily_row else None,
        weekly_rollup=_rollup_entry(weekly_row) if weekly_row else None,
        personal_observed_baseline=_baseline_entry(baseline_row) if baseline_row else None,
    )


def get_i8_governed_context_projection(
    db: Session,
    *,
    account_user_id: int,
    measurement_type: str = V1_MEASUREMENT_TYPE,
) -> I8GovernedPhysiologicalContext:
    """Read persisted rollup/baseline rows for the account's SELF-linked subject only."""
    subject = _resolve_self_linked_subject_for_account(db, account_user_id)
    if subject is None:
        return I8GovernedPhysiologicalContext(
            health_subject_id=None,
            measurement_type=measurement_type,
        )
    return _load_bounded_projection_for_subject_row(db, subject=subject, measurement_type=measurement_type)


def projection_context_refs(projection: I8GovernedPhysiologicalContext) -> list[dict[str, Any]]:
    """Bounded provenance refs only — no raw measurement payloads."""
    refs: list[dict[str, Any]] = []
    for entry in (projection.daily_rollup, projection.weekly_rollup):
        if entry is None:
            continue
        refs.append(
            {
                "ref_type": "physiological_measurement_rollup",
                "ref_id": entry.rollup_id,
                "health_subject_id": entry.health_subject_id,
                "measurement_type": entry.measurement_type,
                "bucket_kind": entry.bucket_kind,
            }
        )
    if projection.personal_observed_baseline is not None:
        b = projection.personal_observed_baseline
        refs.append(
            {
                "ref_type": "physiological_baseline",
                "ref_id": b.baseline_id,
                "health_subject_id": b.health_subject_id,
                "measurement_type": b.measurement_type,
                "baseline_method": b.baseline_method,
            }
        )
    return refs


def projection_row_count(projection: I8GovernedPhysiologicalContext) -> int:
    return sum(
        1
        for entry in (
            projection.daily_rollup,
            projection.weekly_rollup,
            projection.personal_observed_baseline,
        )
        if entry is not None
    )
