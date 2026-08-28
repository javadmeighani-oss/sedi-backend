"""I9 aggregation + personal baseline scheduled sweeps — dormant unless enabled."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.aggregation_service import (
    find_rollup_row,
    rebuild_daily_bucket,
    rebuild_higher_bucket_from_daily_rollups,
)
from backend.app.services.i9.baseline_service import (
    BASELINE_SCOPE_V1,
    find_baseline_row,
    upsert_personal_observed_baseline,
)
from backend.app.services.i9.health_subject_service import preferred_language_for_subject
from backend.app.services.i9.i7_producer_service import produce_i7_pattern_from_latest_rollup
from backend.app.services.i9.time_buckets import bucket_bounds, iter_bucket_starts

I9_AGGREGATION_BASELINE_JOBS_FLAG = "SEDI_I9_AGGREGATION_BASELINE_JOBS_ENABLED"
JOB_TIMEZONE = "Asia/Tehran"
DAILY_JOB_ID = "i9_aggregation_baseline_daily"
WEEKLY_JOB_ID = "i9_aggregation_baseline_weekly"
CALENDAR_MONTH_JOB_ID = "i9_aggregation_baseline_calendar_month"
YEARLY_JOB_ID = "i9_aggregation_baseline_yearly"
JOB_IDS: dict[str, str] = {
    "daily": DAILY_JOB_ID,
    "weekly": WEEKLY_JOB_ID,
    "calendar_month": CALENDAR_MONTH_JOB_ID,
    "yearly": YEARLY_JOB_ID,
}
BUCKET_KINDS = tuple(JOB_IDS.keys())
_I9_ADVISORY_LOCK_KEY = 0x49394A31  # dedicated I9 scheduled-runtime key ('I9J1')
I9_SCHEDULED_RUNTIME_ADVISORY_LOCK_KEY = _I9_ADVISORY_LOCK_KEY
MAX_ATTEMPTS_PER_SUBJECT = 2
DEFAULT_SUBJECT_BATCH_SIZE = 500
LATE_DATA_LOOKBACK_DAYS: dict[str, int] = {
    "daily": 7,
    "weekly": 14,
    "calendar_month": 35,
    "yearly": 370,
}
REQUIRED_OBS_FIELDS = (
    "bucket_kind",
    "scheduled_time",
    "started_at",
    "completed_at",
    "status",
    "subjects_scanned",
    "subjects_eligible",
    "subjects_processed",
    "subjects_failed",
    "rollups_created",
    "rollups_rebuilt",
    "baselines_created",
    "baselines_rebuilt",
    "baselines_unchanged",
    "i7_written",
    "i7_skipped",
    "lock_acquired",
    "failures",
    "retry_count",
    "duration",
    "job_id",
    "next_run_time",
    "enabled",
    "detail",
)


def i9_aggregation_baseline_jobs_enabled() -> bool:
    return os.getenv(I9_AGGREGATION_BASELINE_JOBS_FLAG, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def subject_batch_size() -> int:
    raw = os.getenv("SEDI_I9_AGGREGATION_BASELINE_SUBJECT_BATCH", str(DEFAULT_SUBJECT_BATCH_SIZE))
    try:
        return max(1, min(5000, int(raw)))
    except ValueError:
        return DEFAULT_SUBJECT_BATCH_SIZE


def aggregation_baseline_cron_kwargs(bucket_kind: str) -> dict[str, object]:
    """Cron offsets after I7 period-summary jobs to avoid collision (Asia/Tehran)."""
    if bucket_kind == "daily":
        spec = {"hour": 1, "minute": 10}
    elif bucket_kind == "weekly":
        spec = {"day_of_week": "mon", "hour": 1, "minute": 20}
    elif bucket_kind == "calendar_month":
        spec = {"day": 1, "hour": 1, "minute": 30}
    elif bucket_kind == "yearly":
        spec = {"month": 1, "day": 1, "hour": 1, "minute": 40}
    else:
        raise ValueError("INVALID_BUCKET_KIND")
    return {
        "trigger": "cron",
        "timezone": JOB_TIMEZONE,
        "max_instances": 1,
        "coalesce": True,
        **spec,
    }


def next_cron_fire(bucket_kind: str, *, now: Optional[datetime] = None) -> str:
    from apscheduler.triggers.cron import CronTrigger

    from backend.app.services.i7.period_summaries import SUMMARY_TZ

    kw = aggregation_baseline_cron_kwargs(bucket_kind)
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


def closed_bucket_anchor(bucket_kind: str, *, now: Optional[datetime] = None) -> datetime:
    """Instant inside the just-closed bucket (reuses I7 closed-period anchor)."""
    from backend.app.services.i7.jobs import closed_period_anchor

    mapping = {
        "daily": "DAILY",
        "weekly": "WEEKLY",
        "calendar_month": "MONTHLY",
        "yearly": "YEARLY",
    }
    return closed_period_anchor(mapping[bucket_kind], now=now)


def _iso(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def eligible_health_subject_ids(
    db: Session,
    *,
    activity_since: datetime,
    batch_size: int,
) -> list[int]:
    rows = (
        db.query(models.PhysiologicalMeasurement.health_subject_id)
        .filter(
            models.PhysiologicalMeasurement.ingestion_status == "accepted",
            models.PhysiologicalMeasurement.measured_at >= activity_since,
            models.PhysiologicalMeasurement.health_subject_id.isnot(None),
        )
        .distinct()
        .order_by(models.PhysiologicalMeasurement.health_subject_id.asc())
        .limit(batch_size)
        .all()
    )
    return [int(r[0]) for r in rows]


@dataclass(frozen=True)
class AggregationBaselineSweepResult:
    bucket_kind: str
    job_id: str
    enabled: bool
    scheduled_time: str
    started_at: str
    completed_at: str
    status: str
    subjects_scanned: int
    subjects_eligible: int
    subjects_processed: int
    subjects_failed: int
    rollups_created: int
    rollups_rebuilt: int
    baselines_created: int
    baselines_rebuilt: int
    baselines_unchanged: int
    i7_written: int
    i7_skipped: int
    lock_acquired: bool
    failures: int
    retry_count: int
    duration: str
    next_run_time: str
    detail: str


def format_i9_run_log(result: AggregationBaselineSweepResult) -> str:
    parts = [
        "I9_RUN",
        f"bucket_kind={result.bucket_kind}",
        f"scheduled_time={result.scheduled_time}",
        f"started_at={result.started_at}",
        f"completed_at={result.completed_at}",
        f"status={result.status}",
        f"subjects_scanned={result.subjects_scanned}",
        f"subjects_eligible={result.subjects_eligible}",
        f"subjects_processed={result.subjects_processed}",
        f"subjects_failed={result.subjects_failed}",
        f"rollups_created={result.rollups_created}",
        f"rollups_rebuilt={result.rollups_rebuilt}",
        f"baselines_created={result.baselines_created}",
        f"baselines_rebuilt={result.baselines_rebuilt}",
        f"baselines_unchanged={result.baselines_unchanged}",
        f"i7_written={result.i7_written}",
        f"i7_skipped={result.i7_skipped}",
        f"lock_acquired={str(result.lock_acquired).lower()}",
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
    bucket_kind: str,
    *,
    job_id: str,
    scheduled_time: str,
    next_run_time: str,
    started: datetime,
    t0: float,
) -> AggregationBaselineSweepResult:
    completed = datetime.now(timezone.utc)
    return AggregationBaselineSweepResult(
        bucket_kind=bucket_kind,
        job_id=job_id,
        enabled=False,
        scheduled_time=scheduled_time,
        started_at=_iso(started),
        completed_at=_iso(completed),
        status="DORMANT_FLAG_OFF",
        subjects_scanned=0,
        subjects_eligible=0,
        subjects_processed=0,
        subjects_failed=0,
        rollups_created=0,
        rollups_rebuilt=0,
        baselines_created=0,
        baselines_rebuilt=0,
        baselines_unchanged=0,
        i7_written=0,
        i7_skipped=0,
        lock_acquired=False,
        failures=0,
        retry_count=0,
        duration=f"{max(0.0, time.monotonic() - t0):.3f}s",
        next_run_time=next_run_time,
        detail="DORMANT_FLAG_OFF",
    )


def _try_advisory_lock(db: Session) -> bool:
    r = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _I9_ADVISORY_LOCK_KEY})
    return bool(r.scalar() if r else False)


def _advisory_unlock(db: Session) -> None:
    try:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _I9_ADVISORY_LOCK_KEY})
    except Exception:
        pass


def _rebuild_rollups_for_subject(
    db: Session,
    *,
    subject: models.HealthSubject,
    bucket_kind: str,
    ref: datetime,
    preferred_language: Optional[str],
    persist: bool,
) -> tuple[int, int]:
    created = rebuilt = 0
    lookback_days = LATE_DATA_LOOKBACK_DAYS[bucket_kind]
    _, period_end = bucket_bounds(bucket_kind, ref=ref, preferred_language=preferred_language)
    range_start = ref - timedelta(days=lookback_days)
    range_end = period_end

    for d_start, d_end in iter_bucket_starts(
        "daily",
        range_start=range_start,
        range_end=range_end,
        preferred_language=preferred_language,
    ):
        had = find_rollup_row(
            db,
            health_subject_id=subject.id,
            measurement_type=BASELINE_SCOPE_V1,
            bucket_kind="daily",
            bucket_start=d_start,
        )
        rebuild_daily_bucket(
            db,
            subject=subject,
            measurement_type=BASELINE_SCOPE_V1,
            ref=d_start,
            preferred_language=preferred_language,
            commit=False,
        )
        if had is None:
            created += 1
        else:
            rebuilt += 1

    if bucket_kind != "daily":
        had_higher = find_rollup_row(
            db,
            health_subject_id=subject.id,
            measurement_type=BASELINE_SCOPE_V1,
            bucket_kind=bucket_kind,
            bucket_start=bucket_bounds(bucket_kind, ref=ref, preferred_language=preferred_language)[0],
        )
        rebuild_higher_bucket_from_daily_rollups(
            db,
            subject=subject,
            measurement_type=BASELINE_SCOPE_V1,
            bucket_kind=bucket_kind,  # type: ignore[arg-type]
            ref=ref,
            preferred_language=preferred_language,
            commit=False,
        )
        if had_higher is None:
            created += 1
        else:
            rebuilt += 1

    if persist:
        db.commit()
    else:
        db.flush()
    return created, rebuilt


def _process_one_subject(
    db: Session,
    *,
    subject_id: int,
    bucket_kind: str,
    ref: datetime,
    persist: bool,
) -> tuple[int, int, int, int, int, int, int]:
    """Returns created, rebuilt, bl_created, bl_rebuilt, bl_unchanged, i7_written, i7_skipped."""
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == subject_id).first()
    if subject is None:
        raise ValueError("SUBJECT_NOT_FOUND")
    lang = preferred_language_for_subject(db, subject)
    r_created, r_rebuilt = _rebuild_rollups_for_subject(
        db,
        subject=subject,
        bucket_kind=bucket_kind,
        ref=ref,
        preferred_language=lang,
        persist=False,
    )
    from backend.app.services.i9.baseline_service import compute_personal_observed_baseline

    computed = compute_personal_observed_baseline(
        db, health_subject_id=subject.id, ref=ref, preferred_language=lang
    )
    bl_before = find_baseline_row(
        db,
        health_subject_id=subject.id,
        measurement_type=BASELINE_SCOPE_V1,
        window_start=computed.window_start,
    )
    bl_before_value = bl_before.baseline_value if bl_before is not None else None
    bl_row = upsert_personal_observed_baseline(db, subject=subject, ref=ref, commit=False)
    if bl_row is None:
        bl_created = bl_rebuilt = bl_unchanged = 0
    elif bl_before is None:
        bl_created = 1
        bl_rebuilt = 0
        bl_unchanged = 0
    elif bl_row.id == bl_before.id and bl_row.baseline_value == bl_before_value:
        bl_created = 0
        bl_rebuilt = 0
        bl_unchanged = 1
    else:
        bl_created = 0
        bl_rebuilt = 1
        bl_unchanged = 0

    if persist:
        db.commit()
    else:
        db.flush()

    producer_bucket: Literal["daily", "weekly", "calendar_month", "yearly"] = (
        bucket_kind if bucket_kind != "daily" else "weekly"
    )
    i7 = produce_i7_pattern_from_latest_rollup(
        db,
        health_subject_id=subject.id,
        measurement_type=BASELINE_SCOPE_V1,
        bucket_kind=producer_bucket,
        commit=persist,
    )
    i7_written = 1 if i7.get("status") == "WRITTEN" else 0
    i7_skipped = 0 if i7_written else 1
    return r_created, r_rebuilt, bl_created, bl_rebuilt, bl_unchanged, i7_written, i7_skipped


def run_aggregation_baseline_sweep(
    db: Session,
    bucket_kind: str,
    *,
    now: Optional[datetime] = None,
    persist: bool = True,
    job_id: Optional[str] = None,
    scheduled_time: str = "",
    next_run_time: str = "",
    acquire_lock: bool = True,
) -> AggregationBaselineSweepResult:
    if bucket_kind not in BUCKET_KINDS:
        raise ValueError("INVALID_BUCKET_KIND")
    t0 = time.monotonic()
    started = datetime.now(timezone.utc)
    resolved_job_id = job_id or JOB_IDS[bucket_kind]

    if not i9_aggregation_baseline_jobs_enabled():
        return _dormant_result(
            bucket_kind,
            job_id=resolved_job_id,
            scheduled_time=scheduled_time,
            next_run_time=next_run_time,
            started=started,
            t0=t0,
        )

    lock_acquired = False
    if acquire_lock:
        if db.bind is not None and db.bind.dialect.name != "postgresql":
            lock_acquired = True
        else:
            lock_acquired = _try_advisory_lock(db)
            if not lock_acquired:
                completed = datetime.now(timezone.utc)
                return AggregationBaselineSweepResult(
                    bucket_kind=bucket_kind,
                    job_id=resolved_job_id,
                    enabled=True,
                    scheduled_time=scheduled_time,
                    started_at=_iso(started),
                    completed_at=_iso(completed),
                    status="LOCK_NOT_ACQUIRED",
                    subjects_scanned=0,
                    subjects_eligible=0,
                    subjects_processed=0,
                    subjects_failed=0,
                    rollups_created=0,
                    rollups_rebuilt=0,
                    baselines_created=0,
                    baselines_rebuilt=0,
                    baselines_unchanged=0,
                    i7_written=0,
                    i7_skipped=0,
                    lock_acquired=False,
                    failures=0,
                    retry_count=0,
                    duration=f"{max(0.0, time.monotonic() - t0):.3f}s",
                    next_run_time=next_run_time,
                    detail="LOCK_NOT_ACQUIRED",
                )

    anchor = closed_bucket_anchor(bucket_kind, now=now)
    lookback_days = LATE_DATA_LOOKBACK_DAYS[bucket_kind]
    activity_since = anchor - timedelta(days=lookback_days)
    batch = subject_batch_size()
    subjects_scanned = int(db.query(models.HealthSubject).count())
    subject_ids = eligible_health_subject_ids(db, activity_since=activity_since, batch_size=batch)
    subjects_eligible = len(subject_ids)

    rollups_created = rollups_rebuilt = 0
    baselines_created = baselines_rebuilt = baselines_unchanged = 0
    i7_written = i7_skipped = 0
    subjects_processed = subjects_failed = failures = retry_count = 0

    try:
        for sid in subject_ids:
            ok = False
            for attempt in range(1, MAX_ATTEMPTS_PER_SUBJECT + 1):
                try:
                    rc, rr, bc, br, bu, iw, isk = _process_one_subject(
                        db,
                        subject_id=sid,
                        bucket_kind=bucket_kind,
                        ref=anchor,
                        persist=True,
                    )
                    rollups_created += rc
                    rollups_rebuilt += rr
                    baselines_created += bc
                    baselines_rebuilt += br
                    baselines_unchanged += bu
                    i7_written += iw
                    i7_skipped += isk
                    subjects_processed += 1
                    ok = True
                    break
                except Exception:
                    db.rollback()
                    if attempt < MAX_ATTEMPTS_PER_SUBJECT:
                        retry_count += 1
                        continue
                    subjects_failed += 1
                    failures += 1
            if not ok:
                continue
    finally:
        if acquire_lock and lock_acquired and db.bind is not None and db.bind.dialect.name == "postgresql":
            _advisory_unlock(db)

    if failures:
        status = "PARTIAL_FAILURES"
        detail = "PARTIAL_FAILURES"
    elif subjects_eligible == 0:
        status = "SUCCESSFUL_NO_OP"
        detail = "NO_ELIGIBLE_SUBJECTS"
    else:
        status = "SUCCESS"
        detail = "OK"

    completed = datetime.now(timezone.utc)
    return AggregationBaselineSweepResult(
        bucket_kind=bucket_kind,
        job_id=resolved_job_id,
        enabled=True,
        scheduled_time=scheduled_time,
        started_at=_iso(started),
        completed_at=_iso(completed),
        status=status,
        subjects_scanned=subjects_scanned,
        subjects_eligible=subjects_eligible,
        subjects_processed=subjects_processed,
        subjects_failed=subjects_failed,
        rollups_created=rollups_created,
        rollups_rebuilt=rollups_rebuilt,
        baselines_created=baselines_created,
        baselines_rebuilt=baselines_rebuilt,
        baselines_unchanged=baselines_unchanged,
        i7_written=i7_written,
        i7_skipped=i7_skipped,
        lock_acquired=lock_acquired,
        failures=failures,
        retry_count=retry_count,
        duration=f"{max(0.0, time.monotonic() - t0):.3f}s",
        next_run_time=next_run_time,
        detail=detail,
    )
