# backend.app.services.notifications.send_guard_v1
"""
Send Guard V1: single entry for all send-path checks.

Order: A) Adaptive pause (companion) -> B) Quiet hours -> C) Dedup -> D) Cap (companion).
Returns allowed, reasons list, and optional dedupe_key, cap, paused_until.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.models import Notification
from backend.app.services.notifications.adaptive_policy_v1 import (
    compute_adaptive_state,
    is_companion_send_allowed,
)
from backend.app.services.notification_runtime.quiet_hours import is_within_quiet_hours

COMPANION_DEDUPE_PREFIX = "companion:"
COMPANION_DEDUPE_LEGACY_PREFIX = "companion_"


def _count_companion_today(db: Session, user_id: int, now: datetime) -> int:
    """Count companion notifications today (canonical + legacy dedupe_key)."""
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.created_at >= start_of_day,
            Notification.dedupe_key.isnot(None),
            or_(
                Notification.dedupe_key.like(f"{COMPANION_DEDUPE_PREFIX}%"),
                Notification.dedupe_key.like(f"{COMPANION_DEDUPE_LEGACY_PREFIX}%"),
            ),
        )
        .count()
    )


def _dedupe_exists(db: Session, user_id: int, dedupe_key: str) -> bool:
    """True if a notification already exists for this user with this dedupe_key."""
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.dedupe_key == dedupe_key,
        )
        .first()
        is not None
    )


def can_send_v1(
    db: Session,
    user_id: int,
    channel: str,
    template_key: Optional[str],
    priority: str,
    now: datetime,
    language: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Single guard for all send paths. Checks in order: pause -> quiet_hours -> dedup -> cap.

    Returns:
        allowed: bool
        reasons: list of str (e.g. ["paused","quiet_hours","dedup","cap"])
        dedupe_key: str | None (computed if template_key present)
        cap: int | None (companion cap override when companion)
        paused_until: str | None (ISO when paused)
    """
    reasons: List[str] = []
    dedupe_key: Optional[str] = None
    cap: Optional[int] = None
    paused_until: Optional[str] = None
    priority_lower = (priority or "normal").strip().lower()

    # Map channel for quiet_hours (expects morning | engagement | health_alert)
    qh_channel = "engagement" if channel == "companion" else channel

    # A) Adaptive pause (companion only)
    if channel == "companion":
        allowed_pause, pause_reason = is_companion_send_allowed(db, user_id, now, days=7)
        if not allowed_pause:
            reasons.append("paused")
            state = compute_adaptive_state(db, user_id, now, days=7)
            paused_until = state.get("paused_until")

    # B) Quiet hours (health_alert + critical bypasses; force bypasses quiet)
    if not force and not (channel == "health_alert" and priority_lower == "critical"):
        if is_within_quiet_hours(db, user_id, qh_channel, priority_lower):
            reasons.append("quiet_hours")

    # C) Dedup (when template_key present)
    if template_key:
        date_str = now.strftime("%Y-%m-%d")
        dedupe_key = f"{channel}:{template_key}:{user_id}:{date_str}"
        if _dedupe_exists(db, user_id, dedupe_key):
            reasons.append("dedup")

    # D) Cap (companion only)
    if channel == "companion":
        state = compute_adaptive_state(db, user_id, now, days=7)
        cap = state.get("companion_cap_override", 2)
        count_today = _count_companion_today(db, user_id, now)
        if count_today >= cap:
            reasons.append("cap")

    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
        "dedupe_key": dedupe_key,
        "cap": cap,
        "paused_until": paused_until,
    }
