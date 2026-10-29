# backend.app.services.notifications.adaptive_policy_v1
"""
Adaptive Policy V1 (R-023): reactions ADAPT the companion notifications, they never switch them off.

Javad 2026-10-26: when the user dislikes (or dismisses) a notification Sedi must learn from it and change the TIMING,
the TEXT TYPE or the FOLLOW-UP style - never stop sending. So there is no adaptive pause any more
(``paused_until`` is kept in the state only for API compatibility and is always None).

What each reaction changes (last N days, default 7; the effect fades after the window):
- dislike reason wrong_timing  -> timing.avoid_hours_utc: the hour of the disliked notification (+-1h) is avoided,
                                  so the next one goes out at a different time of day.
- dislike reason too_frequent  -> companion_cap_override = 1 (one a day at most) - softer, not silent.
- dislike reason irrelevant / not_helpful -> content_hints.avoid_topic (do not reference the past topic).
- dislike reason unclear       -> content_hints.simple_copy (plainest wording).
- dismiss >= 3 (ignored)       -> the hours of the ignored notifications are avoided and the cap becomes 1.
- dislike >= 2                 -> cap 1; dislike >= 3 -> content_hints.lighter_touch (plain caring check-in:
                                  no topic recap, simplest wording) - the follow-up changes style.
- like >= 2                    -> cap 2 (no reduction).
- open does not change anything.

P7 (2026-10-27): a dislike WITHOUT a reason (the tray button has no UI to ask) is understood from evidence instead of
being ignored - see ``infer_dislike_reasons``. The user's own reason always wins for that notification.

A guard keeps the adaptation from muting a user by accident: at most ``MAX_AVOID_HOURS`` distinct hours (3) are avoided,
each widened by one hour -> at most 9 of the 24 hours of the day are ever skipped.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

SKIP_REASONS = frozenset({"too_frequent", "wrong_timing", "busy_now", "rest_time", "not_in_mood"})  # frequency / timing reasons (R-023: adapt, never pause)
TIMING_REASONS = frozenset({"wrong_timing", "busy_now", "rest_time", "not_in_mood"})  # "not now": another time of day
FREQUENCY_REASONS = frozenset({"too_frequent"})
TOPIC_AVOID_REASONS = frozenset({"irrelevant", "not_helpful"})
SIMPLE_REASONS = frozenset({"unclear"})
SKIP_REASON_WINDOW_DAYS = 3  # kept for importers; no longer used to pause
MAX_AVOID_HOURS = 3

from sqlalchemy.orm import Session

from backend.app.models import Notification, NotificationFeedback


def _hour_band(hour: int) -> List[int]:
    return [(hour - 1) % 24, hour % 24, (hour + 1) % 24]


NIGHT_START_HOUR = 22  # local hours [22, 24) and [0, 7) count as "the middle of the night"
NIGHT_END_HOUR = 7
MANY_IN_24H = 3  # this many notifications within 24h before the disliked one = "too frequent"
_TOPIC_TEMPLATE_CUES = ("continu", "follow", "recap", "topic", "checkin", "check_in", "initiative")


def _user_zone(db: Session, user_id: int):
    import pytz

    try:
        from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone

        return pytz.timezone(resolve_validated_user_timezone(db, user_id))
    except Exception:
        return pytz.timezone("Asia/Tehran")


def infer_dislike_reasons(db: Session, user_id: int, notification: Notification, zone=None) -> List[str]:
    """Deterministic understanding of WHY a notification was disliked when the user gave no reason (P7).

    Evidence, in order: (1) it arrived in the middle of the user's night -> wrong_timing; (2) three or more notifications
    in the 24h before it -> too_frequent; (3) it was a follow-up / topic recap -> irrelevant (do not reference the past
    topic); (4) otherwise the safest change: no topic recap and the plainest wording (not_helpful + unclear).
    Returns bounded reason names (the same vocabulary the user could have chosen)."""
    import pytz

    stamp = notification.sent_at or notification.created_at
    if stamp is None:
        return ["not_helpful", "unclear"]
    zone = zone or _user_zone(db, user_id)
    aware = stamp if stamp.tzinfo else pytz.UTC.localize(stamp)
    local_hour = aware.astimezone(zone).hour
    if local_hour >= NIGHT_START_HOUR or local_hour < NIGHT_END_HOUR:
        return ["wrong_timing"]
    since = stamp - timedelta(hours=24)
    recent = (
        db.query(Notification.id)
        .filter(Notification.user_id == user_id, Notification.created_at >= since, Notification.created_at <= stamp)
        .count()
    )
    if recent >= MANY_IN_24H:
        return ["too_frequent"]
    marker = " ".join(
        str(x or "") for x in (notification.template_key, notification.category, notification.source_type)
    ).lower()
    if any(cue in marker for cue in _TOPIC_TEMPLATE_CUES):
        return ["irrelevant"]
    return ["not_helpful", "unclear"]


def _notification_hours(db: Session, notification_ids: List[int]) -> Dict[int, int]:
    """UTC hour of day when each notification was sent (falls back to its creation time)."""
    if not notification_ids:
        return {}
    rows = db.query(Notification).filter(Notification.id.in_(notification_ids)).all()
    out: Dict[int, int] = {}
    for n in rows:
        stamp = n.sent_at or n.created_at
        if stamp is not None:
            out[int(n.id)] = int(stamp.hour)
    return out


def compute_adaptive_state(
    db: Session,
    user_id: int,
    now: datetime,
    days: int = 7,
) -> Dict[str, Any]:
    """
    Compute the adaptive state for the companion channel from feedback in the last `days` days.

    Returns:
        paused_until: always None (R-023 - reactions never stop sending)
        companion_cap_override: 1 or 2
        timing: { avoid_hours_utc: [0..23], wrong_timing: bool }
        counts: { like, dislike, open, dismiss }
        reasons_count: optional { reason: count } from meta_json
        content_hints: { avoid_topic, simple_copy, lighter_touch }
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
    avoid_topic = False
    simple_copy = False
    too_frequent = False
    wrong_timing = False
    timing_sources: List[tuple] = []  # (created_at, notification_id) of reactions about the time of day
    # P7: dislikes that carry no reason are understood from evidence (the user's own reason always wins).
    explained_ids = set()
    for r in rows:
        if r.action == "dislike" and r.meta_json:
            try:
                import json as _json

                if (_json.loads(r.meta_json) or {}).get("reason"):
                    explained_ids.add(r.notification_id)
            except (TypeError, ValueError, AttributeError):
                pass
    inferred_count: Dict[str, int] = {}
    inferred_for: set = set()
    zone = None
    for r in rows:
        if r.action in counts:
            counts[r.action] = counts[r.action] + 1
        reason = None
        if r.meta_json:
            try:
                import json

                meta = json.loads(r.meta_json)
                reason = meta.get("reason")
            except (TypeError, ValueError, AttributeError):
                reason = None
        inferred: List[str] = []
        if (
            not reason
            and r.action == "dislike"
            and r.notification_id is not None
            and r.notification_id not in explained_ids
            and r.notification_id not in inferred_for
        ):
            try:
                note = db.query(Notification).filter(Notification.id == r.notification_id).first()
                if note is not None:
                    zone = zone or _user_zone(db, user_id)
                    inferred = infer_dislike_reasons(db, user_id, note, zone)
                    inferred_for.add(r.notification_id)
            except Exception:
                inferred = []
        for reason_name in ([reason] if reason else []) + inferred:
            if reason_name in inferred:
                inferred_count[reason_name] = inferred_count.get(reason_name, 0) + 1
            else:
                reasons_count[reason_name] = reasons_count.get(reason_name, 0) + 1
            if reason_name in TOPIC_AVOID_REASONS:
                avoid_topic = True
            if reason_name in SIMPLE_REASONS:
                simple_copy = True
            if reason_name in FREQUENCY_REASONS:
                too_frequent = True
            if reason_name in TIMING_REASONS:
                wrong_timing = True
                timing_sources.append((r.created_at, r.notification_id))
        if r.action == "dismiss":
            timing_sources.append((r.created_at, r.notification_id))

    # Softening only (never silence): one companion notification a day after repeated negative reactions.
    companion_cap_override = 2
    if counts.get("dislike", 0) >= 2 or counts.get("dismiss", 0) >= 3 or too_frequent:
        companion_cap_override = 1

    # Timing: avoid the hours of the notifications the user found badly timed or kept ignoring.
    avoid_hours: List[int] = []
    if wrong_timing or counts.get("dismiss", 0) >= 3:
        recent = sorted(
            (t for t in timing_sources if t[1] is not None),
            key=lambda t: t[0] or since,
            reverse=True,
        )
        hours_by_id = _notification_hours(db, [int(t[1]) for t in recent])
        distinct: List[int] = []
        for _created, nid in recent:
            h = hours_by_id.get(int(nid))
            if h is not None and h not in distinct:
                distinct.append(h)
            if len(distinct) >= MAX_AVOID_HOURS:
                break
        seen = set()
        for h in distinct:
            for band_hour in _hour_band(h):
                if band_hour not in seen:
                    seen.add(band_hour)
                    avoid_hours.append(band_hour)
        avoid_hours.sort()

    lighter_touch = counts.get("dislike", 0) >= 3
    return {
        "paused_until": None,
        "companion_cap_override": companion_cap_override,
        "timing": {"avoid_hours_utc": avoid_hours, "wrong_timing": wrong_timing},
        "counts": counts,
        "reasons_count": reasons_count,
        "inferred_reasons_count": inferred_count,
        "content_hints": {
            "avoid_topic": avoid_topic,
            "simple_copy": simple_copy,
            "lighter_touch": lighter_touch,
        },
        "computed_at": now.isoformat(),
        "days": days,
    }


def is_in_avoid_hours(state: Dict[str, Any], now: datetime) -> bool:
    """True when `now` (UTC) falls in an hour the user's reactions asked Sedi to avoid."""
    try:
        hours = (state.get("timing") or {}).get("avoid_hours_utc") or []
        return int(now.hour) in set(int(h) for h in hours)
    except Exception:
        return False


def is_companion_send_allowed(
    db: Session,
    user_id: int,
    now: datetime,
    days: int = 7,
) -> tuple:
    """
    Returns (allowed: bool, reason: str).

    R-023: reactions never pause sending, so this is always (True, ""). The function stays so the older call sites
    (notification engine, send guard) keep working; the effect of reactions is expressed through
    `compute_adaptive_state` (cap, avoid hours, content hints).
    """
    return True, ""
