"""I10 helpers for plan-aware notifications (Stage 06 / B2-D4): today's plan progress and feedback-aware throttling.

Read-only. Reuses I8 (plan actions, review state) and the existing NotificationFeedback rows; no new storage.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

# Bounded dislike reasons (I10 interaction vocabulary) and what each one asks the digest to do.
SKIP_ON_REASONS = frozenset({"too_frequent", "wrong_timing"})
AVOID_GENERIC_ON_REASONS = frozenset({"irrelevant", "not_helpful", "unclear"})
PAUSE_DISLIKES_7D = 3


def _pres(raw: Optional[str]) -> dict:
    try:
        v = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def day_progress(db: Session, user_id: int, local_day: date) -> Optional[dict]:
    """Progress of the catalog-composed plan items of `local_day`, or None when the day has none."""
    from backend.app.services.i8.action_review import review_of
    from backend.app.services.i8.plan_composer import SOURCE_TAG

    plans = (
        db.query(models.I8OperationalPlan)
        .filter(models.I8OperationalPlan.user_id == user_id, models.I8OperationalPlan.user_local_date == local_day)
        .all()
    )
    if not plans:
        return None
    actions = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == user_id,
            models.I8OperationalPlanAction.plan_id.in_([p.id for p in plans]),
        )
        .all()
    )
    done = skipped = pending = 0
    nxt: list[str] = []
    for a in actions:
        pres = _pres(a.presentation_json)
        if pres.get("source") != SOURCE_TAG or not pres.get("local_time"):
            continue  # rest days / non-composer actions are not tracked here
        rev = review_of(a)
        if rev and rev["outcome"] == "done":
            done += 1
        elif rev:
            skipped += 1
        else:
            pending += 1
            if len(nxt) < 2:
                nxt.append(f"{pres.get('local_time')} {(a.summary_text or '').strip()[:60]}")
    total = done + skipped + pending
    if total == 0:
        return None
    return {"done": done, "skipped": skipped, "pending": pending, "total": total, "next": nxt}


def state_from_feedback(rows: list, when: datetime) -> dict:
    """Pure: what recent feedback rows ask of the daily digest.

    skip: do not send today (too_frequent / wrong_timing in the last 3 days, or >= 3 dislikes in 7 days).
    avoid_generic: do not send the generic check-in (irrelevant / not_helpful / unclear dislikes in 7 days).
    """
    dislikes = recent_skip = generic_votes = 0
    for r in rows:
        if r.action != "dislike":
            continue
        dislikes += 1
        reason = str(_pres(r.meta_json).get("reason") or "")
        created = r.created_at
        if reason in SKIP_ON_REASONS and created is not None and created >= when - timedelta(days=3):
            recent_skip += 1
        if reason in AVOID_GENERIC_ON_REASONS:
            generic_votes += 1
    return {
        "skip": recent_skip >= 1 or dislikes >= PAUSE_DISLIKES_7D,
        "avoid_generic": generic_votes >= 1 or dislikes >= 2,
        "dislikes_7d": dislikes,
    }


def feedback_state(db: Session, user_id: int, now: Optional[datetime] = None) -> dict:
    when = now or datetime.now(timezone.utc)
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc).replace(tzinfo=None)
    rows = (
        db.query(models.NotificationFeedback)
        .filter(models.NotificationFeedback.user_id == user_id, models.NotificationFeedback.created_at >= when - timedelta(days=7))
        .all()
    )
    return state_from_feedback(rows, when)
