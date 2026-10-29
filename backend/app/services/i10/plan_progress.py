"""I10 helpers for plan-aware notifications (Stage 06 / B2-D4): today's plan progress and feedback-aware throttling.

Read-only. Reuses I8 (plan actions, review state) and the existing NotificationFeedback rows; no new storage.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

# Bounded dislike reasons (I10 interaction vocabulary) and what each one asks the digest to do (R-023: ADAPT, never stop).
SHIFT_TIME_REASONS = frozenset({"wrong_timing", "too_frequent", "busy_now", "rest_time", "not_in_mood"})  # send at another time of day
SKIP_ON_REASONS = SHIFT_TIME_REASONS  # kept for importers
AVOID_GENERIC_ON_REASONS = frozenset({"irrelevant", "not_helpful"})  # a more practical text instead of the hello
SIMPLE_ON_REASONS = frozenset({"unclear"})  # the plainest, shortest text
PAUSE_DISLIKES_7D = 3  # kept for importers; many dislikes now only make the text lighter, never stop it

DEFAULT_DIGEST_LOCAL_TIME = "09:00"
SHIFTED_DIGEST_LOCAL_TIME = "17:30"


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
    """Pure: what recent feedback rows ask of the daily digest (R-023 - reactions adapt it, they never cut it off).

    skip: always False (kept for callers; a dislike never silences the digest).
    shift_time: send the digest at another time of day (wrong_timing / too_frequent dislike in the last 7 days).
    avoid_generic: use a practical text, not the generic hello (irrelevant / not_helpful, or >= 2 dislikes).
    simple: use the plainest, shortest text (unclear reason, or >= 3 dislikes).
    """
    dislikes = shift = generic_votes = simple_votes = 0
    for r in rows:
        if r.action != "dislike":
            continue
        dislikes += 1
        reason = str(_pres(r.meta_json).get("reason") or "")
        if reason in SHIFT_TIME_REASONS:
            shift += 1
        if reason in AVOID_GENERIC_ON_REASONS:
            generic_votes += 1
        if reason in SIMPLE_ON_REASONS:
            simple_votes += 1
    return {
        "skip": False,
        "shift_time": shift >= 1,
        "avoid_generic": generic_votes >= 1 or dislikes >= 2,
        "simple": simple_votes >= 1 or dislikes >= PAUSE_DISLIKES_7D,
        "dislikes_7d": dislikes,
    }


def preferred_digest_local_time(db: Session, user_id: int) -> str:
    """Local HH:MM for the user's daily digest: 09:00, or the evening slot after a timing/frequency dislike.

    Fail-open: any problem returns the default slot.
    """
    try:
        if feedback_state(db, user_id)["shift_time"]:
            return SHIFTED_DIGEST_LOCAL_TIME
    except Exception:
        pass
    return DEFAULT_DIGEST_LOCAL_TIME


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
