"""I7 bounded derived continuity on existing UserPeriodSummary.DAILY. Not a new store."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_READ, _active_consent, has_permission
from backend.app.services.i7.period_summaries import period_bounds, resolve_week_start
from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone

logger = logging.getLogger(__name__)

GENERATOR = "i7-bounded-continuity-v1"
_TOPIC_MAX = 80


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_topic(text: Optional[str]) -> Optional[str]:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return None
    if len(cleaned) > _TOPIC_MAX:
        cleaned = cleaned[: _TOPIC_MAX - 1].rstrip() + "…"
    return cleaned


def parse_bounded_continuity(row: Optional[models.UserPeriodSummary]) -> dict:
    if row is None:
        return {}
    try:
        data = json.loads(row.structured_summary_json or "{}")
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    bc = data.get("bounded_continuity")
    if not isinstance(bc, dict):
        return {}
    topic = _safe_topic(str(bc.get("topic") or ""))
    if not topic:
        return {}
    return bc


def should_project_derived_continuity(db: Session, user_id: int) -> bool:
    """Derived plane is supporting context only when no eligible raw remains."""
    if not has_permission(db, user_id, PERM_READ):
        return False
    from backend.app.services.i7.retention import query_eligible_raw

    if query_eligible_raw(db, user_id, limit=1):
        return False
    return get_bounded_continuity_topic(db, user_id) is not None


def get_bounded_continuity_topic(db: Session, user_id: int) -> Optional[str]:
    """I6 read-governed derived topic from latest active DAILY summary."""
    if not has_permission(db, user_id, PERM_READ):
        return None
    from backend.app.services.i7.hierarchy import get_canonical_daily

    row = get_canonical_daily(db, user_id)
    bc = parse_bounded_continuity(row)
    topic = _safe_topic(str(bc.get("topic") or ""))
    if topic:
        return topic
    return None


def refresh_bounded_continuity(
    db: Session,
    *,
    user_id: int,
    memory: models.Memory,
) -> Optional[models.UserPeriodSummary]:
    """Write today's DAILY bounded_continuity via I7 version/supersede, never mutate finalized."""
    topic = _safe_topic(getattr(memory, "user_message", None))
    if not topic:
        return None
    from backend.app.services.i7.hierarchy import (
        _active_for_period,
        _canonical_json,
        _integrity,
        _next_version,
    )

    tz_name = resolve_validated_user_timezone(db, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    week_start = resolve_week_start(getattr(user, "preferred_language", None) if user else None)
    import pytz

    zone = pytz.timezone(tz_name)
    start, end = period_bounds("DAILY", now=_utcnow(), week_start=week_start, tz=zone)
    consent = _active_consent(db, user_id=user_id)
    prior = _active_for_period(db, user_id, "DAILY", start)
    bc = {
        "topic": topic,
        "source_memory_id": int(memory.id),
        "not_transcript": True,
        "not_i9": True,
        "not_i6_fact": True,
    }
    try:
        existing = json.loads(prior.structured_summary_json or "{}") if prior else {}
        if not isinstance(existing, dict):
            existing = {}
    except Exception:
        existing = {}
    payload = dict(existing)
    payload.setdefault("authority", "UserPeriodSummary.DAILY")
    payload.setdefault("source", "ELIGIBLE_GOVERNED_RAW")
    payload.setdefault("generator", GENERATOR)
    payload["not_transcript"] = True
    payload["bounded_continuity"] = bc
    structured = _canonical_json(payload)
    integrity = _integrity(payload)
    if (
        prior is not None
        and prior.status == "active"
        and prior.integrity_sha256 == integrity
        and prior.structured_summary_json == structured
    ):
        return prior
    lineage = {"raw_memory_ids": [int(memory.id)]}
    if prior is not None and prior.lineage_json:
        try:
            old_lineage = json.loads(prior.lineage_json)
            if isinstance(old_lineage, dict):
                ids = [int(x) for x in (old_lineage.get("raw_memory_ids") or [])]
                if int(memory.id) not in ids:
                    ids.append(int(memory.id))
                if ids:
                    lineage = {"raw_memory_ids": ids}
        except Exception:
            pass
    version = _next_version(db, user_id, "DAILY", start, prior)
    row = models.UserPeriodSummary(
        user_id=user_id,
        summary_type="DAILY",
        period_start=start,
        period_end=end,
        version=version,
        structured_summary_json=structured,
        narrative_summary=topic,
        evidence_range=json.dumps({"start": start.isoformat(), "end": end.isoformat()}),
        generated_at=_utcnow(),
        status="active",
        finalized_at=None,
        source_complete=False,
        integrity_sha256=integrity,
        lineage_json=json.dumps(lineage),
        period_timezone=tz_name,
        period_week_start=week_start,
        consent_id=consent.id if consent else None,
        provenance_json=json.dumps(
            {"generator": GENERATOR, "layer": "DAILY", "source_memory_id": memory.id},
            sort_keys=True,
        ),
    )
    db.add(row)
    db.flush()
    return row
