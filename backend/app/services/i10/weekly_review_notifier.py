"""Weekly plan review notification (pilot V1 screen 6): on the user's chosen weekday and time Sedi tells how the week went.

Runs inside the existing I8 scan tick (no new scheduler) and through the one I10 intake (gate4 policy, send guard,
reaction adaptation - R-019/R-023). Flag-gated, default OFF. One send per user/domain/local day (candidate-key dedupe).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    sanitize_notification_context,
)
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i10.self_producer_adapter import enqueue_self_scheduler_notification
from backend.app.services.section10.feature_flags import _env_flag_enabled

logger = logging.getLogger(__name__)

WINDOW_HOURS = 3
_TITLE = {
    "nutrition": {"fa": "مرور هفته‌ی برنامه‌ی غذایی", "en": "Your meal-plan week", "ar": "مراجعة أسبوع الخطة الغذائية"},
    "exercise": {"fa": "مرور هفته‌ی ورزشت", "en": "Your exercise week", "ar": "مراجعة أسبوع التمرين"},
}
_FAMILY = {
    "nutrition": I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP,
    "exercise": I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP,
}


def weekly_review_enabled() -> bool:
    return _env_flag_enabled("SEDI_I8_WEEKLY_REVIEW_ENABLED")


def _local_now(tz_name: str, now_utc: datetime) -> datetime:
    from zoneinfo import ZoneInfo

    return now_utc.astimezone(ZoneInfo(tz_name))


def _is_review_moment(local_now: datetime, settings: dict) -> bool:
    if local_now.isoweekday() != int(settings["review_weekday"]):
        return False
    hh, mm = (int(x) for x in str(settings["review_time"]).split(":"))
    start = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return start <= local_now <= start + timedelta(hours=WINDOW_HOURS)


def process_weekly_reviews(db: Session, *, now_utc: Optional[datetime] = None, force: bool = False, limit: int = 300) -> int:
    """Send the due weekly reviews. Returns how many notifications were enqueued."""
    if not force and not weekly_review_enabled():
        return 0
    from backend.app.services.i8.local_day import local_today_for_user
    from backend.app.services.i8.plan_settings import DOMAINS, get_plan_settings
    from backend.app.services.i8.weekly_review import build_weekly_review

    when = (now_utc or datetime.now(timezone.utc))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    user_ids = [
        int(r[0])
        for r in db.query(models.I8OperationalPlanAction.user_id)
        .filter(models.I8OperationalPlanAction.status == "ACTIVE")
        .distinct()
        .limit(limit)
        .all()
    ]
    sent = 0
    for uid in user_ids:
        try:
            tz_name, local_today = local_today_for_user(db, uid, now_utc=when)
            local_now = _local_now(tz_name, when)
            row = db.query(models.User.preferred_language).filter(models.User.id == uid).first()
            lang = ((row[0] if row and row[0] else "fa") or "fa").strip().lower().split("-")[0]
            lang = lang if lang in ("fa", "en", "ar") else "en"
            for domain in DOMAINS:
                settings = get_plan_settings(db, uid, domain, lang)
                if not _is_review_moment(local_now, settings):
                    continue
                review = build_weekly_review(db, uid, domain, language=lang, now_utc=when)
                if review.get("state") not in ("ready", "active", "review_due") or not review.get("total"):
                    continue
                key = f"i10:self:weekly_review:{uid}:{domain}:{local_today.isoformat()}"
                payload = NotificationPayload(
                    user_id=uid,
                    type="connection_ping",
                    title=_TITLE[domain][lang],
                    body=review["message"],
                    priority="normal",
                    dedupe_key=key,
                    metadata={"alert_code": "i8_weekly_review", "action_domain": domain, "cycle_start": review.get("cycle_start")},
                    category=NotificationCategory.CARE_FOLLOW_UP.value,
                    source_type=NotificationSourceType.USER_GOAL.value,
                    source_id=f"weekly_review:{domain}",
                    risk_level=NotificationRiskLevel.INFORMATIONAL.value,
                    template_key="weekly_plan_review",
                    context=sanitize_notification_context(
                        {"template_key": "weekly_plan_review", "trigger_reason": "i8_weekly_review", "action_hint": domain}
                    ),
                    privacy_class="PRIVATE",
                )
                notif = enqueue_self_scheduler_notification(
                    db,
                    user_id=uid,
                    payload=payload,
                    semantic_family=_FAMILY[domain],
                    candidate_key=key,
                    source_type="i8_weekly_review",
                    source_id=f"{domain}:{local_today.isoformat()}",
                )
                if notif is not None:
                    sent += 1
        except Exception:
            db.rollback()
            logger.exception("[I8-weekly-review] user=%s failed", uid)
    return sent
