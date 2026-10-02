"""I7 period-summary jobs — dormant unless enabled. No schema change."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from backend.app.services.i6.memory_writes import list_facts_or_empty
from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile
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
JOB_IDS = {
    "DAILY": DAILY_JOB_ID,
    "WEEKLY": WEEKLY_JOB_ID,
    "MONTHLY": MONTHLY_JOB_ID,
    "YEARLY": YEARLY_JOB_ID,
}
MAX_ATTEMPTS_PER_USER = 2
REQUIRED_OBS_FIELDS = (
    "period_type",
    "scheduled_time",
    "started_at",
    "completed_at",
    "status",
    "users_scanned",
    "users_eligible",
    "users_skipped_no_consent",
    "summaries_created",
    "summaries_rebuilt",
    "summaries_unchanged",
    "failures",
    "retry_count",
    "duration",
    "job_id",
    "next_run_time",
)


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


def next_cron_fire(summary_type: str, *, now: Optional[datetime] = None) -> str:
    """Next cron fire as UTC ISO. Does not use APScheduler Job.next_run_time."""
    from apscheduler.triggers.cron import CronTrigger

    kw = period_summary_cron_kwargs(summary_type)
    trigger_kw = {
        k: v
        for k, v in kw.items()
        if k in {"hour", "minute", "day_of_week", "day", "month", "timezone"}
    }
    trigger = CronTrigger(**trigger_kw)
    tz = SUMMARY_TZ
    if now is None:
        aware = datetime.now(tz)
    elif now.tzinfo is None:
        aware = tz.localize(now)
    else:
        aware = now.astimezone(tz)
    nxt = trigger.get_next_fire_time(None, aware)
    if nxt is None:
        return ""
    if nxt.tzinfo is None:
        nxt = tz.localize(nxt)
    return nxt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _iso(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class PeriodSummarySweepResult:
    summary_type: str
    job_id: str
    enabled: bool
    scheduled_time: str
    started_at: str
    completed_at: str
    status: str
    users_scanned: int
    users_eligible: int
    users_skipped_no_consent: int
    summaries_created: int
    summaries_rebuilt: int
    summaries_unchanged: int
    failures: int
    retry_count: int
    duration: str
    next_run_time: str
    detail: str

    @property
    def period_type(self) -> str:
        return self.summary_type

    @property
    def users_seen(self) -> int:
        return self.users_eligible

    @property
    def rebuilt(self) -> int:
        return self.summaries_created + self.summaries_rebuilt

    @property
    def skipped(self) -> int:
        return self.summaries_unchanged

    @property
    def failed(self) -> int:
        return self.failures


def format_i7_run_log(result: PeriodSummarySweepResult) -> str:
    parts = [
        "I7_RUN",
        f"period_type={result.period_type}",
        f"scheduled_time={result.scheduled_time}",
        f"started_at={result.started_at}",
        f"completed_at={result.completed_at}",
        f"status={result.status}",
        f"users_scanned={result.users_scanned}",
        f"users_eligible={result.users_eligible}",
        f"users_skipped_no_consent={result.users_skipped_no_consent}",
        f"summaries_created={result.summaries_created}",
        f"summaries_rebuilt={result.summaries_rebuilt}",
        f"summaries_unchanged={result.summaries_unchanged}",
        f"failures={result.failures}",
        f"retry_count={result.retry_count}",
        f"duration={result.duration}",
        f"job_id={result.job_id}",
        f"next_run_time={result.next_run_time}",
        f"detail={result.detail}",
        f"enabled={str(result.enabled).lower()}",
    ]
    return " ".join(parts)


def _dormant_result(
    summary_type: str,
    *,
    job_id: str,
    scheduled_time: str,
    next_run_time: str,
    started: datetime,
    t0: float,
) -> PeriodSummarySweepResult:
    completed = datetime.now(timezone.utc)
    return PeriodSummarySweepResult(
        summary_type=summary_type,
        job_id=job_id,
        enabled=False,
        scheduled_time=scheduled_time,
        started_at=_iso(started),
        completed_at=_iso(completed),
        status="DORMANT_FLAG_OFF",
        users_scanned=0,
        users_eligible=0,
        users_skipped_no_consent=0,
        summaries_created=0,
        summaries_rebuilt=0,
        summaries_unchanged=0,
        failures=0,
        retry_count=0,
        duration=f"{max(0.0, time.monotonic() - t0):.3f}s",
        next_run_time=next_run_time,
        detail="DORMANT_FLAG_OFF",
    )


def run_period_summary_sweep(
    db: Session,
    summary_type: str,
    *,
    now: Optional[datetime] = None,
    persist: bool = True,
    job_id: Optional[str] = None,
    scheduled_time: str = "",
    next_run_time: str = "",
) -> PeriodSummarySweepResult:
    if summary_type not in SUMMARY_TYPES:
        raise PeriodSummaryError("INVALID_SUMMARY_TYPE")
    t0 = time.monotonic()
    started = datetime.now(timezone.utc)
    resolved_job_id = job_id or JOB_IDS[summary_type]
    if not period_summary_jobs_enabled():
        return _dormant_result(
            summary_type,
            job_id=resolved_job_id,
            scheduled_time=scheduled_time,
            next_run_time=next_run_time,
            started=started,
            t0=t0,
        )
    anchor = closed_period_anchor(summary_type, now=now)
    users_scanned = int(db.query(models.User).count())
    users = consented_memory_user_ids(db)
    users_eligible = len(users)
    users_skipped_no_consent = max(0, users_scanned - users_eligible)
    created = rebuilt = unchanged = failures = retry_count = 0
    for uid in users:
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
        row = None
        for attempt in range(1, MAX_ATTEMPTS_PER_USER + 1):
            try:
                row = rebuild_summary(db, uid, summary_type, now=anchor, commit=persist)
                break
            except Exception:
                if persist:
                    db.rollback()
                if attempt < MAX_ATTEMPTS_PER_USER:
                    retry_count += 1
                    continue
                failures += 1
        if row is None:
            continue
        if prior_id is None:
            created += 1
        elif row.id == prior_id:
            unchanged += 1
        else:
            rebuilt += 1
    if failures:
        status = "PARTIAL_FAILURES"
        detail = "PARTIAL_FAILURES"
    elif users_eligible == 0:
        status = "SUCCESSFUL_NO_OP"
        detail = "NO_ELIGIBLE_USERS"
    else:
        status = "SUCCESS"
        detail = "OK"
    completed = datetime.now(timezone.utc)
    return PeriodSummarySweepResult(
        summary_type=summary_type,
        job_id=resolved_job_id,
        enabled=True,
        scheduled_time=scheduled_time,
        started_at=_iso(started),
        completed_at=_iso(completed),
        status=status,
        users_scanned=users_scanned,
        users_eligible=users_eligible,
        users_skipped_no_consent=users_skipped_no_consent,
        summaries_created=created,
        summaries_rebuilt=rebuilt,
        summaries_unchanged=unchanged,
        failures=failures,
        retry_count=retry_count,
        duration=f"{max(0.0, time.monotonic() - t0):.3f}s",
        next_run_time=next_run_time,
        detail=detail,
    )


@dataclass(frozen=True)
class LifelongProfileSweepResult:
    enabled: bool
    persist: bool
    users_scanned: int
    users_eligible: int
    users_skipped_no_consent: int
    profiles_created: int
    profiles_rebuilt: int
    profiles_skipped_active: int
    profiles_skipped_no_facts: int
    failures: int
    retry_count: int
    detail: str


def format_lifelong_run_log(result: LifelongProfileSweepResult) -> str:
    parts = [
        "I7_LIFELONG_RUN",
        f"enabled={str(result.enabled).lower()}",
        f"persist={str(result.persist).lower()}",
        f"users_scanned={result.users_scanned}",
        f"users_eligible={result.users_eligible}",
        f"users_skipped_no_consent={result.users_skipped_no_consent}",
        f"profiles_created={result.profiles_created}",
        f"profiles_rebuilt={result.profiles_rebuilt}",
        f"profiles_skipped_active={result.profiles_skipped_active}",
        f"profiles_skipped_no_facts={result.profiles_skipped_no_facts}",
        f"failures={result.failures}",
        f"retry_count={result.retry_count}",
        f"detail={result.detail}",
    ]
    return " ".join(parts)


def _active_lifelong_profile(
    db: Session, user_id: int
) -> Optional[models.UserLifelongProfile]:
    return (
        db.query(models.UserLifelongProfile)
        .filter(
            models.UserLifelongProfile.user_id == user_id,
            models.UserLifelongProfile.status == "active",
        )
        .order_by(models.UserLifelongProfile.version.desc())
        .first()
    )


def _any_lifelong_profile(db: Session, user_id: int) -> bool:
    return (
        db.query(models.UserLifelongProfile.id)
        .filter(models.UserLifelongProfile.user_id == user_id)
        .first()
        is not None
    )


def run_lifelong_profile_sweep(
    db: Session, *, persist: bool = True
) -> LifelongProfileSweepResult:
    """Bounded I7-owned lifelong profile refresh. No chat/I8 write coupling.

    Rebuilds only when:
    - PERM_READ holds and readable I6 facts exist, AND
    - no active lifelong profile (missing OR previously invalidated/stale).

    Active current profiles are skipped. Empty profiles are never created.
    When persist=False, performs eligibility accounting without mutation.
    """
    enabled = period_summary_jobs_enabled()
    users_scanned = int(db.query(models.User).count())
    if not enabled and persist:
        # Flag-off persistent path: zero mutation (scheduler should not call this).
        return LifelongProfileSweepResult(
            enabled=False,
            persist=persist,
            users_scanned=users_scanned,
            users_eligible=0,
            users_skipped_no_consent=0,
            profiles_created=0,
            profiles_rebuilt=0,
            profiles_skipped_active=0,
            profiles_skipped_no_facts=0,
            failures=0,
            retry_count=0,
            detail="DORMANT_FLAG_OFF",
        )

    users = consented_memory_user_ids(db)
    users_eligible = len(users)
    users_skipped_no_consent = max(0, users_scanned - users_eligible)
    created = rebuilt = skipped_active = skipped_no_facts = failures = retry_count = 0

    for uid in users:
        if not has_permission(db, uid, PERM_READ):
            users_skipped_no_consent += 1
            users_eligible = max(0, users_eligible - 1)
            continue
        facts = list_facts_or_empty(db, uid)
        if not facts:
            skipped_no_facts += 1
            continue
        active = _active_lifelong_profile(db, uid)
        if active is not None:
            skipped_active += 1
            continue
        had_prior = _any_lifelong_profile(db, uid)
        if not persist:
            # Dry-run eligibility only — no rebuild mutation.
            if had_prior:
                rebuilt += 1
            else:
                created += 1
            continue
        row = None
        for attempt in range(1, MAX_ATTEMPTS_PER_USER + 1):
            try:
                row = rebuild_lifelong_profile(db, uid, commit=True)
                break
            except Exception:
                db.rollback()
                if attempt < MAX_ATTEMPTS_PER_USER:
                    retry_count += 1
                    continue
                failures += 1
        if row is None:
            continue
        if had_prior:
            rebuilt += 1
        else:
            created += 1

    if failures:
        detail = "PARTIAL_FAILURES"
    elif users_eligible == 0:
        detail = "NO_ELIGIBLE_USERS"
    else:
        detail = "OK"
    return LifelongProfileSweepResult(
        enabled=enabled,
        persist=persist,
        users_scanned=users_scanned,
        users_eligible=users_eligible,
        users_skipped_no_consent=users_skipped_no_consent,
        profiles_created=created,
        profiles_rebuilt=rebuilt,
        profiles_skipped_active=skipped_active,
        profiles_skipped_no_facts=skipped_no_facts,
        failures=failures,
        retry_count=retry_count,
        detail=detail,
    )
