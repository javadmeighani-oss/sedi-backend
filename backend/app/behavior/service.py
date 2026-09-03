# backend/app/behavior/service.py
"""Behavior Layer V1: service (profile CRUD, apply to question, companion_ping creation)."""
import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

import pytz
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.behavior.config import is_behavior_v1_enabled
from backend.app.behavior.policy import BehaviorPolicy
from backend.app.behavior.models import BehaviorMode
from backend.app.behavior.texts_fa import get_lead_in, get_companion_ping_body, get_companion_ping_title

logger = logging.getLogger("uvicorn.error")

_COMPANION_PING_TYPE = "companion_ping"
_COMPANION_PING_CHANNEL = "engagement"
_DEEPLINK_TEMPLATE = "sedi://chat?from=notif&type=companion_ping"


def _today_utc(now: datetime) -> date:
    if hasattr(now, "date"):
        return now.date()
    return date(now.year, now.month, now.day)


def _user_local_date(db: Session, user_id: int, utc_dt: datetime) -> date:
    """Return calendar date of utc_dt in user's local timezone (same logic as quiet_hours)."""
    try:
        from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone

        tz_str = resolve_validated_user_timezone(db, user_id)
        user_tz = pytz.timezone(tz_str)
    except Exception:
        user_tz = pytz.timezone("Asia/Tehran")
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=pytz.UTC)
    return utc_dt.astimezone(user_tz).date()


def get_or_create_profile(db: Session, user_id: int, now: Optional[datetime] = None) -> models.UserBehaviorProfile:
    """Get or create UserBehaviorProfile; reset daily count if day changed."""
    if now is None:
        now = datetime.utcnow()
    today = _today_utc(now)
    row = db.query(models.UserBehaviorProfile).filter(models.UserBehaviorProfile.user_id == user_id).first()
    if not row:
        row = models.UserBehaviorProfile(
            user_id=user_id,
            score=0.5,
            mode="normal",
            daily_initiated_count=0,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    # Reset daily count when calendar day changed (last initiation was on a previous day)
    if row.last_initiated_at is not None and _today_utc(row.last_initiated_at) < today:
        row.daily_initiated_count = 0
        db.commit()
        db.refresh(row)
    return row


def record_initiated(db: Session, user_id: int, now: Optional[datetime] = None) -> None:
    """
    Record one Sedi-initiated action. Reset daily_initiated_count when last_initiated_at is null
    or on a different user-local calendar day; then set count to 1 and last_initiated_at=now.
    Deterministic and safe under repeated calls (same day: count stays 1).
    """
    if now is None:
        now = datetime.utcnow()
    profile = get_or_create_profile(db, user_id, now)
    today = _user_local_date(db, user_id, now)
    if profile.last_initiated_at is None or _user_local_date(db, user_id, profile.last_initiated_at) != today:
        profile.daily_initiated_count = 0
    profile.daily_initiated_count = 1
    profile.last_initiated_at = now
    profile.updated_at = now
    db.commit()


def record_interaction(db: Session, user_id: int, now: Optional[datetime] = None) -> None:
    """Update last_interaction_at (e.g. when user sends a message)."""
    if now is None:
        now = datetime.utcnow()
    profile = get_or_create_profile(db, user_id, now)
    profile.last_interaction_at = now
    profile.updated_at = now
    db.commit()


def apply_behavior_to_question(
    db: Session,
    user_id: int,
    data: Dict[str, Any],
    lang: str,
) -> Dict[str, Any]:
    """
    When BEHAVIOR_V1_ENABLED: optionally prepend caring lead-in and keep tone.
    When disabled: return data unchanged (zero effect).
    """
    if not is_behavior_v1_enabled():
        return data
    profile = get_or_create_profile(db, user_id)
    policy = BehaviorPolicy()
    mode = policy.mode_from_score(float(profile.score))
    if not policy.should_add_lead_in(mode, data.get("question_type")):
        return data
    lead_in = get_lead_in(lang or "fa")
    text = (data.get("text") or "").strip()
    if not text:
        return data
    # Prepend lead-in only if not already present (idempotent)
    if lead_in and not text.startswith(lead_in.strip()):
        data = {**data, "text": lead_in + text}
    return data


def try_create_companion_ping_notification(
    db: Session,
    user_id: int,
    lang: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[models.Notification]:
    """
    If BEHAVIOR_V1_ENABLED and policy allows (quiet hours, daily cap, cooldown, initiated_today),
    create one companion_ping notification; otherwise return None.
    Deep link: sedi://chat?from=notif&type=companion_ping.
    """
    if not is_behavior_v1_enabled():
        return None
    if now is None:
        now = datetime.utcnow()
    profile = get_or_create_profile(db, user_id, now)
    today = _user_local_date(db, user_id, now)
    initiated_today = (
        profile.last_initiated_at is not None
        and _user_local_date(db, user_id, profile.last_initiated_at) == today
    )
    policy = BehaviorPolicy()
    allowed, reason = policy.can_initiate(
        db,
        user_id,
        now,
        daily_initiated_count=profile.daily_initiated_count or 0,
        last_initiated_at=profile.last_initiated_at,
        initiated_today=initiated_today,
    )
    logger.info(
        "[BEHAVIOR_V1] %s reason=%s user_id=%s now=%s qh_runtime=%s",
        "allowed" if allowed else "blocked",
        reason or "ok",
        user_id,
        now.isoformat(),
        policy.use_quiet_hours_runtime,
    )
    if not allowed:
        return None
    lang = (lang or "fa").strip().lower()
    if lang not in ("en", "fa", "ar"):
        lang = "fa"
    title = get_companion_ping_title(lang)
    body = get_companion_ping_body(lang)
    date_str = now.strftime("%Y-%m-%d")
    dedupe_key = f"companion_ping:{user_id}:{date_str}"
    # Dedupe: one per user per day
    existing = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.dedupe_key == dedupe_key,
        )
        .first()
    )
    if existing:
        return None
    from backend.app.schemas.notification import NotificationPayload
    from backend.app.services.gate4.notification_context import (
        NotificationCategory,
        NotificationRiskLevel,
        NotificationSourceType,
        build_scheduler_context,
    )
    from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily
    from backend.app.services.i10.self_producer_adapter import (
        build_self_occurrence_key,
        enqueue_self_scheduler_notification,
    )

    payload = NotificationPayload(
        user_id=user_id,
        type=_COMPANION_PING_TYPE,
        title=title,
        body=body,
        priority="normal",
        scheduled_for=now,
        dedupe_key=dedupe_key,
        metadata={"language": lang, "legacy_type": "companion_ping"},
        category=NotificationCategory.ENGAGEMENT_CHECKIN.value,
        source_type=NotificationSourceType.SYSTEM_SCHEDULER.value,
        template_key="companion_ping",
        risk_level=NotificationRiskLevel.NORMAL.value,
        context=build_scheduler_context(
            job_id="companion_ping",
            template_key="companion_ping",
            trigger_reason="engagement_checkin",
        ),
    )
    occurrence_key = build_self_occurrence_key("companion", user_id=user_id, scheduled_for=now)
    notif = enqueue_self_scheduler_notification(
        db,
        user_id=user_id,
        payload=payload,
        semantic_family=I10SemanticFamily.ENGAGEMENT_NUDGE,
        candidate_key=occurrence_key,
        source_type="companion_ping",
        source_id=date_str,
        privacy_class=I10PrivacyClass.PUBLIC_SAFE,
    )
    if notif is None:
        return None
    # Preserve Behavior V1 deeplink/actions contract after canonical intake.
    notif.deeplink_url = _DEEPLINK_TEMPLATE
    notif.actions_json = '[{"id":"open_chat","type":"OPEN_CHAT"}]'
    notif.channel = _COMPANION_PING_CHANNEL
    notif.language = lang
    notif.type = _COMPANION_PING_TYPE
    db.add(notif)
    db.commit()
    db.refresh(notif)
    record_initiated(db, user_id, now)
    return notif
