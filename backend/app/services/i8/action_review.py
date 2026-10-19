"""I8 end-of-day / end-of-week plan review (Stage 06 / B1.5-c).

The user (or a reminder reply) marks a plan action done or skipped (+ a bounded reason). `done` uses the existing
I8 completion authority (ACTIVE -> COMPLETED). `skipped` is recorded in the action's presentation JSON
(`review`), so no status/schema change is needed (the DB status set is fixed). Adherence summaries feed the
Lifestyle week review and the next composed week (low adherence -> lighter plan).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from backend.app import models

REVIEW_OUTCOMES = ("done", "skipped")
SKIP_REASONS = ("no_time", "too_hard", "not_feeling_well", "dont_like", "forgot", "other")
LOW_ADHERENCE_PERCENT = 40


class ActionReviewError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def _load(raw: Optional[str]) -> dict:
    try:
        val = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return val if isinstance(val, dict) else {}


def review_of(action: Any) -> Optional[dict]:
    """The recorded review of an action: {"outcome": "done"|"skipped", "reason": ...} or None."""
    if (getattr(action, "status", "") or "").upper() == "COMPLETED":
        return {"outcome": "done"}
    rev = _load(getattr(action, "presentation_json", None)).get("review")
    return rev if isinstance(rev, dict) and rev.get("outcome") in REVIEW_OUTCOMES else None


def record_review(
    db: Session,
    *,
    actor_user_id: int,
    action_id: int,
    outcome: str,
    reason: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Owner-only. done -> I8 completion; skipped -> `review` in presentation_json. Idempotent."""
    if outcome not in REVIEW_OUTCOMES:
        raise ActionReviewError("INVALID_OUTCOME")
    if reason is not None and reason not in SKIP_REASONS:
        raise ActionReviewError("INVALID_REASON")
    action = db.query(models.I8OperationalPlanAction).filter(models.I8OperationalPlanAction.id == int(action_id)).first()
    if action is None:
        raise ActionReviewError("ACTION_NOT_FOUND")
    if int(action.user_id) != int(actor_user_id):
        raise ActionReviewError("ACTION_OWNER_MISMATCH")
    when = now or datetime.now(timezone.utc)
    if outcome == "done":
        from backend.app.services.i8.action_completion import I8ActionCompletionError, complete_exact_operational_action

        try:
            complete_exact_operational_action(db, actor_user_id=actor_user_id, action_id=int(action_id), now=when)
        except I8ActionCompletionError as exc:
            raise ActionReviewError(getattr(exc, "code", "ACTION_NOT_COMPLETABLE")) from exc
        db.commit()
        return {"action_id": int(action_id), "outcome": "done"}
    if (action.status or "").upper() != "ACTIVE":
        raise ActionReviewError("ACTION_NOT_REVIEWABLE")
    pres = _load(action.presentation_json)
    pres["review"] = {"outcome": "skipped", "reason": reason or "other", "at": when.isoformat()}
    action.presentation_json = json.dumps(pres, ensure_ascii=False, separators=(",", ":"))
    action.updated_at = when
    db.commit()
    return {"action_id": int(action_id), "outcome": "skipped", "reason": pres["review"]["reason"]}


def adherence(actions: Iterable[Any], *, up_to: Optional[date] = None) -> dict:
    """Counts over the given actions (only those on/before `up_to` local date when provided)."""
    done = skipped = pending = 0
    reasons: dict = {}
    for a in actions:
        pres = _load(getattr(a, "presentation_json", None))
        local = str(pres.get("local_date") or "")
        if up_to is not None and local and local > up_to.isoformat():
            continue
        rev = review_of(a)
        if rev and rev["outcome"] == "done":
            done += 1
        elif rev:
            skipped += 1
            reasons[rev.get("reason", "other")] = reasons.get(rev.get("reason", "other"), 0) + 1
        else:
            pending += 1
    total = done + skipped + pending
    percent = round(100 * done / total) if total else 0
    return {"done": done, "skipped": skipped, "pending": pending, "total": total, "percent": percent, "skip_reasons": reasons}


def last_cycle_adherence_percent(db: Session, user_id: int, domain: str) -> Optional[int]:
    """Adherence % of the user's most recent stamped cycle for `domain`, or None when there is none yet."""
    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(models.I8OperationalPlanAction.user_id == int(user_id), models.I8OperationalPlanAction.action_domain == domain)
        .order_by(models.I8OperationalPlanAction.id.desc())
        .limit(40)
        .all()
    )
    if not rows:
        return None
    from backend.app.services.i8.local_day import CYCLE_START_META_KEY

    last = _load(rows[0].presentation_json).get(CYCLE_START_META_KEY)
    cycle = [a for a in rows if _load(a.presentation_json).get(CYCLE_START_META_KEY) == last]
    summary = adherence(cycle)
    reviewed = summary["done"] + summary["skipped"]
    return summary["percent"] if reviewed >= 3 else None
