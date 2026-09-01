"""I10-B11 daily wellness digest — bounded I9 facts, truthful data-status semantics."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    build_scheduler_context,
    sanitize_notification_context,
)
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i10.self_producer_adapter import resolve_or_ensure_self_health_subject_id
from backend.app.services.i9.i8_projection_service import (
    get_i8_governed_context_projection,
    projection_context_refs,
)

logger = logging.getLogger(__name__)

DIGEST_PRODUCER_OWNER = "I10_DAILY_WELLNESS_DIGEST"
STALE_DATA_HOURS = 48
PARTIAL_COVERAGE_THRESHOLD = 0.5


class DailyWellnessDataStatus(str, Enum):
    SUFFICIENT_OBSERVED_DATA = "SUFFICIENT_OBSERVED_DATA"
    PARTIAL_DATA = "PARTIAL_DATA"
    STALE_DATA = "STALE_DATA"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class DailyWellnessDigestFacts:
    user_id: int
    health_subject_id: Optional[int]
    observation_period_start: datetime
    observation_period_end: datetime
    data_status: DailyWellnessDataStatus
    coverage_summary: str
    recency_summary: str
    alert_summary: str
    limitations: tuple[str, ...] = ()
    provenance_refs: tuple[dict[str, Any], ...] = ()
    i7_continuity_available: bool = False
    baseline_comparison: Optional[str] = None


def build_daily_digest_occurrence_key(*, user_id: int, period_date: date) -> str:
    return f"i10:self:daily_digest:{user_id}:{period_date.isoformat()}"


def _period_bounds(when: datetime) -> tuple[datetime, datetime]:
    day = when.date()
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _load_i7_daily_flag(db: Session, user_id: int) -> bool:
    row = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.status == "active",
        )
        .order_by(models.UserPeriodSummary.period_start.desc())
        .limit(1)
        .first()
    )
    return row is not None and row.finalized_at is not None


def _qualifying_alert_summary(db: Session, user_id: int, period_start: datetime) -> str:
    count = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
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
        return "Recent observations are above your personal observed baseline (not a clinical normal range)."
    if daily.avg_value < baseline.baseline_value:
        return "Recent observations are below your personal observed baseline (not a clinical normal range)."
    return "Recent observations are similar to your personal observed baseline pattern."


def assemble_daily_wellness_digest_facts(
    db: Session,
    *,
    user_id: int,
    when: Optional[datetime] = None,
) -> DailyWellnessDigestFacts:
    """Bounded I9 rollup/baseline projection only — no raw PhysiologicalMeasurement rows."""
    now = when or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    period_start, period_end = _period_bounds(now)

    projection = get_i8_governed_context_projection(db, account_user_id=user_id)
    refs = tuple(projection_context_refs(projection))
    daily = projection.daily_rollup

    limitations: list[str] = []
    data_status = DailyWellnessDataStatus.NO_DATA
    coverage_summary = "No observed health data was available for today's digest period."
    recency_summary = "No recent device-reported data timestamp is available."

    if projection.health_subject_id is None:
        limitations = ("SELF health subject linkage is unavailable.",)
    elif daily is None:
        limitations = ("No daily rollup is available for the observation period.",)
    else:
        age_hours = (now - daily.bucket_end.replace(tzinfo=timezone.utc)).total_seconds() / 3600.0
        if daily.sample_count <= 0:
            data_status = DailyWellnessDataStatus.NO_DATA
            coverage_summary = "No samples were recorded in the daily rollup for this period."
        elif age_hours > STALE_DATA_HOURS:
            data_status = DailyWellnessDataStatus.STALE_DATA
            coverage_summary = "Observed data exists but is older than expected for today."
            recency_summary = f"Latest rollup period ended more than {STALE_DATA_HOURS} hours ago."
        elif daily.coverage is not None and daily.coverage < PARTIAL_COVERAGE_THRESHOLD:
            data_status = DailyWellnessDataStatus.PARTIAL_DATA
            coverage_summary = "Coverage is partial according to the daily rollup metric."
            recency_summary = "Some observed data was received during the period."
        else:
            data_status = DailyWellnessDataStatus.SUFFICIENT_OBSERVED_DATA
            coverage_summary = "Observed data was received during the period."
            recency_summary = "Latest daily rollup covers the recent observation window."

    baseline_cmp = _baseline_comparison_phrase(projection) if projection.health_subject_id else None
    alert_summary = _qualifying_alert_summary(db, user_id, period_start)

    return DailyWellnessDigestFacts(
        user_id=user_id,
        health_subject_id=projection.health_subject_id,
        observation_period_start=period_start,
        observation_period_end=period_end,
        data_status=data_status,
        coverage_summary=coverage_summary,
        recency_summary=recency_summary,
        alert_summary=alert_summary,
        limitations=tuple(limitations),
        provenance_refs=refs,
        i7_continuity_available=_load_i7_daily_flag(db, user_id),
        baseline_comparison=baseline_cmp,
    )


def render_digest_body(facts: DailyWellnessDigestFacts) -> str:
    """Deterministic factual copy — no diagnosis, healthy/normal, or false reassurance."""
    parts = [facts.coverage_summary, facts.recency_summary, facts.alert_summary]
    if facts.baseline_comparison:
        parts.append(facts.baseline_comparison)
    if facts.data_status in (DailyWellnessDataStatus.PARTIAL_DATA, DailyWellnessDataStatus.NO_DATA):
        parts.append(
            "Today's available data is incomplete, so a full comparison is not available."
        )
    if facts.limitations:
        parts.append(facts.limitations[0])
    return " ".join(p for p in parts if p)


def build_daily_wellness_digest_payload(
    facts: DailyWellnessDigestFacts,
    *,
    occurrence_key: str,
    language: str = "en",
) -> NotificationPayload:
    body = render_digest_body(facts)
    context = sanitize_notification_context(
        {
            "template_key": "daily_wellness_digest",
            "trigger_reason": "daily_wellness_digest",
            "schedule_label": facts.observation_period_start.date().isoformat(),
        }
    )
    return NotificationPayload(
        user_id=facts.user_id,
        type="health_alert",
        title="Daily wellness digest",
        body=body,
        priority="normal",
        dedupe_key=occurrence_key,
        metadata={
            "language": language,
            "alert_code": "daily_wellness_digest",
            "data_status": facts.data_status.value,
            "i7_continuity_available": facts.i7_continuity_available,
            "provenance_ref_count": len(facts.provenance_refs),
        },
        category=NotificationCategory.DAILY_STATUS.value,
        source_type=NotificationSourceType.DAILY_ROUTINE.value,
        source_id=facts.observation_period_start.date().isoformat(),
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key="daily_wellness_digest",
        context=context,
        health_subject_id=facts.health_subject_id,
        privacy_class=I10PrivacyClass.HEALTH_SENSITIVE.value,
    )


def enqueue_daily_wellness_digest(
    db: Session,
    *,
    facts: DailyWellnessDigestFacts,
    occurrence_key: str,
    language: str = "en",
) -> Optional[models.Notification]:
    if facts.health_subject_id is None:
        health_subject_id = resolve_or_ensure_self_health_subject_id(db, facts.user_id)
    else:
        health_subject_id = facts.health_subject_id

    payload = build_daily_wellness_digest_payload(facts, occurrence_key=occurrence_key, language=language)
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=facts.user_id,
        notification_scope=I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
        source_owner=DIGEST_PRODUCER_OWNER,
        source_type="morning_notifications",
        source_id=facts.observation_period_start.date().isoformat(),
        semantic_family=I10SemanticFamily.DAILY_WELLNESS_DIGEST,
        privacy_hint=I10PrivacyClass.HEALTH_SENSITIVE,
        provenance_refs=tuple(
            json.dumps(ref, separators=(",", ":"), sort_keys=True) for ref in facts.provenance_refs
        ),
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B11] suppressed user=%s digest=%s reason=%s",
            facts.user_id,
            occurrence_key,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
