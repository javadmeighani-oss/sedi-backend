# backend.app.services.i10.daily_initiative
"""R-021 / M5: Sedi's daily initiative — she thinks of the user without being asked.

At most ONE gentle message per user per day, chosen from what the second memory knows (recent low mood, a suggestion of her
own that was never followed up, a stated health concern). It reuses the existing I10-B12 CareFollowUpTask worker, so the
message goes through the whole smart-notification framework (I10 queue, send_guard_v1: reactions/quiet hours/caps,
FCM, tap-through). No new scheduler: the sweep is one job in the existing scheduler, behind SEDI_DAILY_INITIATIVE_ENABLED.
Copy is lock-screen-safe: it never names a condition, a feeling's cause or a family member.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

INITIATIVE_TITLE_PREFIX = "initiative:"
KIND_MOOD, KIND_SUGGESTION, KIND_HEALTH = "mood", "suggestion", "health"
MIN_HOURS_BETWEEN = 20
QUIET_AFTER_CHAT_HOURS = 6


def choose_initiative(db: Session, user_id: int) -> Optional[str]:
    """The ONE thing worth saying today, or None (silence is better than noise)."""
    try:
        from backend.app.services.i7.derived_signals import recent_wellbeing_trend

        if (recent_wellbeing_trend(db, user_id) or {}).get("trend") == "low":
            return KIND_MOOD
    except Exception:
        pass
    try:
        from backend.app.services.intelligence.care_continuity import earlier_suggestions

        if earlier_suggestions(db, user_id):
            return KIND_SUGGESTION
    except Exception:
        pass
    try:
        from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

        if any(f.key == "health_concerns" for f in list_facts_readonly_or_empty(db, user_id, domain="medical")):
            return KIND_HEALTH
    except Exception:
        pass
    return None


def _recently_initiated(db: Session, user_id: int, now: datetime) -> bool:
    return (
        db.query(models.CareFollowUpTask.id)
        .filter(
            models.CareFollowUpTask.user_id == user_id,
            models.CareFollowUpTask.title.like(f"{INITIATIVE_TITLE_PREFIX}%"),
            models.CareFollowUpTask.created_at >= now - timedelta(hours=MIN_HOURS_BETWEEN),
        )
        .first()
        is not None
    )


def run_daily_initiative_sweep(db: Session, *, now: Optional[datetime] = None) -> int:
    """Create (not send) the day's initiative tasks; the B12 worker delivers them through the send guard. Fail-open."""
    from backend.app.services.i7.jobs import consented_memory_user_ids
    from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource
    from backend.app.services.i10.contextual_followup_worker import create_structured_follow_up_task
    from backend.app.services.i10.interaction_recorder import get_last_chat_activity_at

    when = now or datetime.utcnow()
    created = 0
    try:
        user_ids = consented_memory_user_ids(db)
    except Exception:
        logger.exception("[M5] consent scan failed")
        return 0
    for uid in user_ids:
        try:
            if _recently_initiated(db, uid, when):
                continue
            last_chat = get_last_chat_activity_at(db, uid)
            if last_chat is not None and (when - last_chat) < timedelta(hours=QUIET_AFTER_CHAT_HOURS):
                continue  # she is already talking with them; no need to knock
            kind = choose_initiative(db, uid)
            if kind is None:
                continue
            create_structured_follow_up_task(
                db,
                user_id=uid,
                title=f"{INITIATIVE_TITLE_PREFIX}{kind}",
                due_at=when,
                source=FollowUpTaskSource.GENERAL_CONTEXTUAL,
                follow_up_kind="daily_initiative",
            )
            db.commit()
            created += 1
        except Exception:
            db.rollback()
            logger.exception("[M5] initiative failed for user=%s", uid)
    return created
