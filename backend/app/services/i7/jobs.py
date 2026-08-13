"""I7 period-summary jobs — dormant unless enabled. No schema change."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import (
    MEMORY_CONSENT_TYPE,
    MEMORY_PURPOSE,
    PERM_READ,
    expire_due_consents,
    has_permission,
)
from backend.app.services.i7.period_summaries import (
    SUMMARY_TZ,
    SUMMARY_TYPES,
    PeriodSummaryError,
    period_bounds,
    rebuild_summary,
)

DAILY_JOB_ID = "i7_period_summary_daily"
WEEKLY_JOB_ID = "i7_period_summary_weekly"
MONTHLY_JOB_ID = "i7_period_summary_monthly"
YEARLY_JOB_ID = "i7_period_summary_yearly"
JOB_TIMEZONE = "Asia/Tehran"


def period_summary_jobs_enabled() -> bool:
    return os.getenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def period_summary_cron_kwargs(summary_type: str) -> dict[str, object]:
    if summary_type == "DAILY":
        spec = {"hour": 0, "minute": 10}
    elif summary_type == "WEEKLY":
        spec = {"day_of_week": "mon", "hour": 0, "minute": 20}
    elif summary_type == "MONTHLY":
        spec = {"day": 1, "hour": 0, "minute": 30}
    elif summary_type == "YEARLY":
        spec = {"month": 1, "day": 1, "hour": 0, "minute": 40}
    else:
        raise PeriodSummaryError("INVALID_SUMMARY_TYPE")
    return {
        "trigger": "cron",
        "timezone": JOB_TIMEZONE,
        "max_instances": 1,
        "coalesce": True,
        **spec,
    }


def closed_period_anchor(summary_type: str, *, now: Optional[datetime] = None) -> datetime:
    """Instant inside the just-closed period so rebuild targets completed windows."""
    tz = SUMMARY_TZ
    if now is None:
        aware = datetime.now(tz)
    elif now.tzinfo is None:
        aware = tz.localize(now)
    else:
        aware = now.astimezone(tz)
    start, _end = period_bounds(summary_type, now=aware)
    return (start - timedelta(seconds=1)).astimezone(tz)


def consented_memory_user_ids(db: Session) -> list[int]:
    expire_due_consents(db, commit=True)
    rows = (
        db.query(models.UserConsent.subject_user_id)
        .filter(
            models.UserConsent.consent_type == MEMORY_CONSENT_TYPE,
            models.UserConsent.purpose == MEMORY_PURPOSE,
            models.UserConsent.status == "active",
        )
        .distinct()
        .all()
    )
    out: list[int] = []
    for (uid,) in rows:
        if has_permission(db, int(uid), PERM_READ):
            out.append(int(uid))
    return out


@dataclass(frozen=True)
class PeriodSummarySweepResult:
    summary_type: str
    enabled: bool
    users_seen: int
    rebuilt: int
    skipped: int
    failed: int
    detail: str


def run_period_summary_sweep(
    db: Session,
    summary_type: str,
    *,
    now: Optional[datetime] = None,
    persist: bool = True,
) -> PeriodSummarySweepResult:
    if summary_type not in SUMMARY_TYPES:
        raise PeriodSummaryError("INVALID_SUMMARY_TYPE")
    if not period_summary_jobs_enabled():
        return PeriodSummarySweepResult(
            summary_type=summary_type,
            enabled=False,
            users_seen=0,
            rebuilt=0,
            skipped=0,
            failed=0,
            detail="DORMANT_FLAG_OFF",
        )
    anchor = closed_period_anchor(summary_type, now=now)
    rebuilt = skipped = failed = 0
    users = consented_memory_user_ids(db)
    for uid in users:
        try:
            prior_active = (
                db.query(models.UserPeriodSummary)
                .filter(
                    models.UserPeriodSummary.user_id == uid,
                    models.UserPeriodSummary.summary_type == summary_type,
                    models.UserPeriodSummary.status == "active",
                )
                .order_by(models.UserPeriodSummary.version.desc())
                .first()
            )
            prior_id = prior_active.id if prior_active is not None else None
            row = rebuild_summary(db, uid, summary_type, now=anchor, commit=persist)
            if prior_id is not None and row.id == prior_id:
                skipped += 1
            else:
                rebuilt += 1
        except Exception:
            failed += 1
    return PeriodSummarySweepResult(
        summary_type=summary_type,
        enabled=True,
        users_seen=len(users),
        rebuilt=rebuilt,
        skipped=skipped,
        failed=failed,
        detail="OK" if failed == 0 else "PARTIAL_FAILURES",
    )
