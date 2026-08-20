"""I7 summary hierarchy: RAW -> DAILY -> WEEKLY -> MONTHLY -> YEARLY -> LIFELONG."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone
from backend.app.services.i6.consent_service import PERM_READ, require_permission, _active_consent
from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile
from backend.app.services.i7.period_summaries import (
    PeriodSummaryError,
    period_bounds,
    resolve_week_start,
)
from backend.app.services.i7.retention import query_eligible_raw_for_local_day

GENERATOR = "i7-wave2-hierarchy-v1"
SUMMARY_TYPES = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
_PARENT = {
    "WEEKLY": "DAILY",
    "MONTHLY": "WEEKLY",
    "YEARLY": "MONTHLY",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _integrity(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _user_period_ctx(db: Session, user_id: int) -> tuple[str, int]:
    tz = resolve_validated_user_timezone(db, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    week_start = resolve_week_start(getattr(user, "preferred_language", None) if user else None)
    return tz, week_start


def _active_for_period(
    db: Session, user_id: int, summary_type: str, period_start: datetime
) -> Optional[models.UserPeriodSummary]:
    return (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == summary_type,
            models.UserPeriodSummary.period_start == period_start,
            models.UserPeriodSummary.status == "active",
        )
        .order_by(models.UserPeriodSummary.version.desc())
        .first()
    )


def _next_version(
    db: Session,
    user_id: int,
    summary_type: str,
    period_start: datetime,
    prior: Optional[models.UserPeriodSummary],
) -> int:
    """Allocate version after max(existing) so stale/superseded rows cannot collide."""
    if prior is not None and prior.status == "active":
        prior.status = "superseded"
        prior.superseded_at = _utcnow()
    max_v = (
        db.query(func.max(models.UserPeriodSummary.version))
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == summary_type,
            models.UserPeriodSummary.period_start == period_start,
        )
        .scalar()
    )
    return int(max_v or 0) + 1


def get_canonical_daily(
    db: Session, user_id: int, *, period_start: Optional[datetime] = None
) -> Optional[models.UserPeriodSummary]:
    q = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.status == "active",
        )
        .order_by(models.UserPeriodSummary.period_start.desc(), models.UserPeriodSummary.version.desc())
    )
    if period_start is not None:
        q = q.filter(models.UserPeriodSummary.period_start == period_start)
    return q.first()


def build_daily_from_raw(
    db: Session,
    user_id: int,
    *,
    now: Optional[datetime] = None,
    finalize: bool = False,
    commit: bool = True,
) -> models.UserPeriodSummary:
    """Canonical DAILY owner is UserPeriodSummary; source = eligible governed raw for closed day."""
    require_permission(db, user_id, PERM_READ)
    tz_name, week_start = _user_period_ctx(db, user_id)
    import pytz

    zone = pytz.timezone(tz_name)
    start, end = period_bounds("DAILY", now=now, week_start=week_start, tz=zone)
    local_day = start.astimezone(zone).date()
    turns = query_eligible_raw_for_local_day(db, user_id, local_day, now=now)
    payload = {
        "authority": "UserPeriodSummary.DAILY",
        "source": "ELIGIBLE_GOVERNED_RAW",
        "generator": GENERATOR,
        "turn_count": len(turns),
        "turn_ids": [t.id for t in turns],
        "not_transcript": True,
    }
    integrity = _integrity(payload)
    consent = _active_consent(db, user_id=user_id)
    prior = _active_for_period(db, user_id, "DAILY", start)
    if (
        prior is not None
        and prior.integrity_sha256 == integrity
        and bool(prior.source_complete) == bool(turns)
        and (prior.finalized_at is not None) == finalize
    ):
        return prior
    version = _next_version(db, user_id, "DAILY", start, prior)
    row = models.UserPeriodSummary(
        user_id=user_id,
        summary_type="DAILY",
        period_start=start,
        period_end=end,
        version=version,
        structured_summary_json=json.dumps(payload, sort_keys=True),
        narrative_summary=f"DAILY summary over {len(turns)} eligible raw turns; not a transcript.",
        evidence_range=json.dumps({"start": start.isoformat(), "end": end.isoformat()}),
        generated_at=_utcnow(),
        status="active",
        finalized_at=_utcnow() if finalize else None,
        source_complete=bool(turns) if finalize else False,
        integrity_sha256=integrity,
        lineage_json=json.dumps({"raw_memory_ids": [t.id for t in turns]}),
        period_timezone=tz_name,
        period_week_start=week_start,
        consent_id=consent.id if consent else None,
        provenance_json=json.dumps({"generator": GENERATOR, "layer": "DAILY"}, sort_keys=True),
    )
    if finalize and turns:
        row.source_complete = True
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def build_higher_from_lower(
    db: Session,
    user_id: int,
    summary_type: str,
    *,
    now: Optional[datetime] = None,
    finalize: bool = False,
    commit: bool = True,
) -> models.UserPeriodSummary:
    if summary_type not in ("WEEKLY", "MONTHLY", "YEARLY"):
        raise PeriodSummaryError("INVALID_SUMMARY_TYPE")
    require_permission(db, user_id, PERM_READ)
    parent_type = _PARENT[summary_type]
    tz_name, week_start = _user_period_ctx(db, user_id)
    import pytz

    zone = pytz.timezone(tz_name)
    start, end = period_bounds(summary_type, now=now, week_start=week_start, tz=zone)
    parents = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == parent_type,
            models.UserPeriodSummary.status == "active",
            models.UserPeriodSummary.finalized_at.isnot(None),
            models.UserPeriodSummary.source_complete.is_(True),
            models.UserPeriodSummary.period_start >= start,
            models.UserPeriodSummary.period_start < end,
        )
        .order_by(models.UserPeriodSummary.period_start.asc())
        .all()
    )
    payload = {
        "authority": f"UserPeriodSummary.{summary_type}",
        "source": f"FINALIZED_{parent_type}",
        "generator": GENERATOR,
        "parent_count": len(parents),
        "parent_ids": [p.id for p in parents],
    }
    integrity = _integrity(payload)
    consent = _active_consent(db, user_id=user_id)
    prior = _active_for_period(db, user_id, summary_type, start)
    if (
        prior is not None
        and prior.integrity_sha256 == integrity
        and bool(prior.source_complete) == bool(parents)
        and (prior.finalized_at is not None) == (finalize and bool(parents))
    ):
        return prior
    version = _next_version(db, user_id, summary_type, start, prior)
    row = models.UserPeriodSummary(
        user_id=user_id,
        summary_type=summary_type,
        period_start=start,
        period_end=end,
        version=version,
        structured_summary_json=json.dumps(payload, sort_keys=True),
        narrative_summary=f"{summary_type} from {len(parents)} finalized {parent_type} summaries.",
        evidence_range=json.dumps({"start": start.isoformat(), "end": end.isoformat()}),
        generated_at=_utcnow(),
        status="active",
        finalized_at=_utcnow() if finalize and parents else None,
        source_complete=bool(parents) if finalize else False,
        integrity_sha256=integrity,
        lineage_json=json.dumps({"parent_summary_ids": [p.id for p in parents]}),
        period_timezone=tz_name,
        period_week_start=week_start,
        consent_id=consent.id if consent else None,
        provenance_json=json.dumps({"generator": GENERATOR, "layer": summary_type}, sort_keys=True),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def build_lifelong_from_yearly(
    db: Session, user_id: int, *, commit: bool = True
) -> models.UserLifelongProfile:
    """LIFELONG derives from finalized YEARLY; still rebuildable profile plane."""
    require_permission(db, user_id, PERM_READ)
    yearly = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "YEARLY",
            models.UserPeriodSummary.status == "active",
            models.UserPeriodSummary.finalized_at.isnot(None),
            models.UserPeriodSummary.source_complete.is_(True),
        )
        .order_by(models.UserPeriodSummary.period_start.desc())
        .all()
    )
    # Keep lifelong builder for profile compaction; stamp yearly lineage into rebuild path.
    profile = rebuild_lifelong_profile(db, user_id, commit=commit)
    if yearly and profile is not None:
        refs = json.loads(profile.source_event_refs_json or "[]")
        refs.append({"yearly_summary_ids": [y.id for y in yearly], "generator": GENERATOR})
        profile.source_event_refs_json = json.dumps(refs)
        if commit:
            db.commit()
            db.refresh(profile)
        else:
            db.flush()
    return profile


def reconcile_stable_fact_via_i6(
    db: Session,
    user_id: int,
    *,
    domain: str,
    key: str,
    value: str,
    commit: bool = True,
) -> models.UserMemoryFact:
    """I7 must not insert UserMemoryFact directly — always I6 governance."""
    from backend.app.services.i6.memory_writes import write_fact

    return write_fact(
        db,
        user_id,
        domain,
        key,
        value,
        source=f"i7_wave2_reconcile:{domain}.{key}",
        provenance_class="i7_derived_candidate",
        commit=commit,
    )
