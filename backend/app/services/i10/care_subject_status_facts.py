"""I10-B14 bounded I9 care-subject status facts — no raw measurements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.i8_projection_service import (
    get_bounded_context_projection_for_subject,
    projection_context_refs,
)

STALE_DATA_HOURS = 48
PARTIAL_COVERAGE_THRESHOLD = 0.5


class CareSubjectDataStatus(str, Enum):
    SUFFICIENT_OBSERVED_DATA = "SUFFICIENT_OBSERVED_DATA"
    PARTIAL_DATA = "PARTIAL_DATA"
    STALE_DATA = "STALE_DATA"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class CareSubjectStatusFacts:
    health_subject_id: int
    observation_period_start: datetime
    observation_period_end: datetime
    data_status: CareSubjectDataStatus
    coverage_summary: str
    recency_summary: str
    alert_summary: str
    limitations: tuple[str, ...] = ()
    provenance_refs: tuple[dict[str, Any], ...] = ()
    baseline_comparison: Optional[str] = None
    latest_bucket_end: Optional[datetime] = None
    has_expected_data_source: bool = False


def _period_bounds(when: datetime) -> tuple[datetime, datetime]:
    day = when.date()
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def subject_has_expected_data_source(db: Session, health_subject_id: int) -> bool:
    """Governed I9 signal that data continuity expectations may apply."""
    binding = (
        db.query(models.DeviceSubjectBinding)
        .filter(
            models.DeviceSubjectBinding.health_subject_id == health_subject_id,
            models.DeviceSubjectBinding.unbound_at.is_(None),
        )
        .limit(1)
        .first()
    )
    if binding is not None:
        return True
    rollup = (
        db.query(models.PhysiologicalMeasurementRollup.id)
        .filter(models.PhysiologicalMeasurementRollup.health_subject_id == health_subject_id)
        .limit(1)
        .first()
    )
    return rollup is not None


def _qualifying_alert_summary(db: Session, health_subject_id: int, period_start: datetime) -> str:
    count = (
        db.query(models.Notification)
        .filter(
            models.Notification.health_subject_id == health_subject_id,
            models.Notification.type == "health_alert",
            models.Notification.created_at >= period_start.replace(tzinfo=None),
        )
        .count()
    )
    if count == 0:
        return "No qualifying alert was recorded during the period."
    return f"{count} qualifying alert(s) were recorded during the period."


def _baseline_comparison_phrase(projection) -> Optional[str]:
    daily = projection.daily_rollup
    baseline = projection.personal_observed_baseline
    if daily is None or baseline is None:
        return None
    if daily.avg_value is None or baseline.baseline_value is None:
        return None
    if daily.avg_value > baseline.baseline_value:
        return (
            "Recent observations are above the subject's personal observed baseline "
            "(not a clinical normal range)."
        )
    if daily.avg_value < baseline.baseline_value:
        return (
            "Recent observations are below the subject's personal observed baseline "
            "(not a clinical normal range)."
        )
    return "Recent observations are similar to the subject's personal observed baseline pattern."


def assemble_care_subject_status_facts(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
) -> CareSubjectStatusFacts:
    """Bounded rollup/baseline projection for any active HealthSubject."""
    now = when or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    period_start, period_end = _period_bounds(now)

    projection = get_bounded_context_projection_for_subject(db, health_subject_id=health_subject_id)
    refs = tuple(projection_context_refs(projection))
    daily = projection.daily_rollup
    expected_source = subject_has_expected_data_source(db, health_subject_id)

    limitations: list[str] = []
    data_status = CareSubjectDataStatus.NO_DATA
    coverage_summary = "No observed health data was available for the observation period."
    recency_summary = "No recent device-reported data timestamp is available."
    latest_bucket_end: Optional[datetime] = None

    if projection.health_subject_id is None:
        limitations = ("Health subject is unavailable or inactive.",)
    elif daily is None:
        limitations = ("No daily rollup is available for the observation period.",)
    else:
        latest_bucket_end = daily.bucket_end
        age_hours = (now - daily.bucket_end.replace(tzinfo=timezone.utc)).total_seconds() / 3600.0
        if daily.sample_count <= 0:
            data_status = CareSubjectDataStatus.NO_DATA
            coverage_summary = "No samples were recorded in the daily rollup for this period."
        elif age_hours > STALE_DATA_HOURS:
            data_status = CareSubjectDataStatus.STALE_DATA
            coverage_summary = "Observed data exists but is older than expected for today."
            recency_summary = f"Latest rollup period ended more than {STALE_DATA_HOURS} hours ago."
        elif daily.coverage is not None and daily.coverage < PARTIAL_COVERAGE_THRESHOLD:
            data_status = CareSubjectDataStatus.PARTIAL_DATA
            coverage_summary = "Coverage is partial according to the daily rollup metric."
            recency_summary = "Some observed data was received during the period."
        else:
            data_status = CareSubjectDataStatus.SUFFICIENT_OBSERVED_DATA
            coverage_summary = "Observed data was received during the period."
            recency_summary = "Latest daily rollup covers the recent observation window."

    baseline_cmp = _baseline_comparison_phrase(projection) if projection.health_subject_id else None
    alert_summary = _qualifying_alert_summary(db, health_subject_id, period_start)

    return CareSubjectStatusFacts(
        health_subject_id=health_subject_id,
        observation_period_start=period_start,
        observation_period_end=period_end,
        data_status=data_status,
        coverage_summary=coverage_summary,
        recency_summary=recency_summary,
        alert_summary=alert_summary,
        limitations=tuple(limitations),
        provenance_refs=refs,
        baseline_comparison=baseline_cmp,
        latest_bucket_end=latest_bucket_end,
        has_expected_data_source=expected_source,
    )
