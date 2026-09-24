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
    """Upsert today's DAILY bounded_continuity from a governed durable raw turn."""
    topic = _safe_topic(getattr(memory, "user_message", None))
    if not topic:
        return None
    tz_name = resolve_validated_user_timezone(db, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    week_start = resolve_week_start(getattr(user, "preferred_language", None) if user else None)
    import pytz

    zone = pytz.timezone(tz_name)
    start, end = period_bounds("DAILY", now=_utcnow(), week_start=week_start, tz=zone)
    consent = _active_consent(db, user_id=user_id)
    row = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.period_start == start,
            models.UserPeriodSummary.status == "active",
        )
        .order_by(models.UserPeriodSummary.version.desc())
        .first()
    )
    payload = {
        "authority": "UserPeriodSummary.DAILY",
        "source": "ELIGIBLE_GOVERNED_RAW",
        "generator": GENERATOR,
        "not_transcript": True,
        "bounded_continuity": {
            "topic": topic,
            "source_memory_id": int(memory.id),
            "not_transcript": True,
            "not_i9": True,
            "not_i6_fact": True,
            "written_at": _utcnow().isoformat(),
        },
    }
    if row is None:
        row = models.UserPeriodSummary(
            user_id=user_id,
            summary_type="DAILY",
            period_start=start,
            period_end=end,
            version=1,
            structured_summary_json=json.dumps(payload, sort_keys=True),
            narrative_summary=topic,
            evidence_range=json.dumps({"start": start.isoformat(), "end": end.isoformat()}),
            generated_at=_utcnow(),
            status="active",
            period_timezone=tz_name,
            period_week_start=week_start,
            consent_id=consent.id if consent else None,
            provenance_json=json.dumps(
                {"generator": GENERATOR, "layer": "DAILY", "source_memory_id": memory.id},
                sort_keys=True,
            ),
        )
        db.add(row)
    else:
        try:
            existing = json.loads(row.structured_summary_json or "{}")
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}
        existing["bounded_continuity"] = payload["bounded_continuity"]
        existing["not_transcript"] = True
        row.structured_summary_json = json.dumps(existing, sort_keys=True)
        row.narrative_summary = topic
        if consent is not None:
            row.consent_id = consent.id
    db.flush()
    return row
