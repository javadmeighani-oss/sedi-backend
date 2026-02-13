# backend.app.services.notifications.adaptive_policy_v1
"""
Adaptive Policy V1 for companion notifications based on feedback history.

Rules (last N days):
- dismiss >= 3 -> paused_until = now + 48h (ignore = dismiss in V1)
- dislike >= 2 -> companion_cap_override = 1/day
- like >= 2 -> companion_cap_override = 2/day (no reduction)
- open does not trigger pause or cap.

Precedence: pause (dismiss >= 3) > cap (dislike >= 2) > like boost (like >= 2).
"""

from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.app.models import NotificationFeedback


def compute_adaptive_state(
    db: Session,
    user_id: int,
    now: datetime,
    days: int = 7,
) -> Dict[str, Any]:
    """
    Compute adaptive state for companion channel from feedback in the last `days` days.

    Returns:
        paused_until: ISO datetime string or None (if dismiss >= 3, now + 48h)
        companion_cap_override: 1 or 2 (1 if dislike >= 2, else 2)
        counts: { like, dislike, open, dismiss }
        reasons_count: optional { reason: count } from meta_json
        computed_at: ISO datetime
    """
    since = now - timedelta(days=days)
    rows = (
        db.query(NotificationFeedback)
        .filter(
            NotificationFeedback.user_id == user_id,
            NotificationFeedback.created_at >= since,
        )
        .all()
    )
    counts = {"like": 0, "dislike": 0, "open": 0, "dismiss": 0}
    reasons_count: Dict[str, int] = {}
    for r in rows:
        if r.action in counts:
            counts[r.action] = counts[r.action] + 1
        if r.meta_json:
            try:
                import json
                meta = json.loads(r.meta_json)
                reason = meta.get("reason")
                if reason:
                    reasons_count[reason] = reasons_count.get(reason, 0) + 1
            except (TypeError, ValueError):
                pass
    # Precedence: pause > cap > like boost
    paused_until = None
    companion_cap_override = 2
    if counts.get("dismiss", 0) >= 3:
        paused_until = (now + timedelta(hours=48)).isoformat()
        companion_cap_override = 2  # when paused we block entirely; cap irrelevant
    elif counts.get("dislike", 0) >= 2:
        companion_cap_override = 1
    elif counts.get("like", 0) >= 2:
        companion_cap_override = 2
    return {
        "paused_until": paused_until,
        "companion_cap_override": companion_cap_override,
        "counts": counts,
        "reasons_count": reasons_count,
        "computed_at": now.isoformat(),
        "days": days,
    }


def is_companion_send_allowed(
    db: Session,
    user_id: int,
    now: datetime,
    days: int = 7,
) -> tuple:
    """
    Returns (allowed: bool, reason: str).
    If paused_until is in the future, allowed=False, reason="paused".
    Otherwise allowed=True, reason="".
    """
    state = compute_adaptive_state(db, user_id, now, days)
    paused_until_str = state.get("paused_until")
    if paused_until_str:
        try:
            s = paused_until_str.replace("Z", "+00:00")
            paused_dt = datetime.fromisoformat(s)
            # Compare: if both naive use as-is; if paused has tz, make now aware
            if paused_dt.tzinfo and now.tzinfo is None:
                from datetime import timezone
                now = now.replace(tzinfo=timezone.utc)
            elif paused_dt.tzinfo is None and now.tzinfo:
                paused_dt = paused_dt.replace(tzinfo=now.tzinfo)
            if paused_dt > now:
                return False, "paused"
        except Exception:
            pass
    return True, ""
