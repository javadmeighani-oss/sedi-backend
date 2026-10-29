"""Sedi's motivation notifications for the exercise plan (pilot V1 screen 7, R-038).

Three kinds, all through the one I10 intake (gate4 policy, send guard, reactions - R-019/R-023), riding the existing I8 scan
tick (no new scheduler), flag-gated, default OFF:
  workout_day - the morning of a workout day (a cheer, or the plain facts after the user disliked cheers),
  comeback    - after a few days without a session: no pressure, one light session,
  milestone   - first session, 5/10/25/50/100 sessions, 2/4/8/12 weeks in a row.
The user's reactions shape each kind: a dislike changes the TIME (wrong_timing / too_frequent), the TEXT TYPE (irrelevant /
not_helpful -> the plain facts; unclear -> the shortest text) and softens the frequency of THAT kind; likes keep it coming.
It never stops because of dislikes (R-023).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
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

KINDS = ("workout_day", "comeback", "milestone")
ALERT_CODE = "i8_motivation"
DEFAULT_LOCAL_TIME = "09:00"
SHIFTED_LOCAL_TIME = "17:30"
WINDOW_HOURS = 3
_TITLE = {
    "fa": {"workout_day": "امروز روز حرکته", "comeback": "من اینجام", "milestone": "آفرین!"},
    "en": {"workout_day": "Today is a move day", "comeback": "I am here", "milestone": "Well done!"},
    "ar": {"workout_day": "اليوم يوم حركة", "comeback": "أنا هنا", "milestone": "أحسنت!"},
}


def motivation_enabled() -> bool:
    return _env_flag_enabled("SEDI_I8_MOTIVATION_ENABLED")


def kind_reaction_state(db: Session, user_id: int, kind: str, now: datetime) -> dict:
    """Likes / dislikes of THIS kind in the last 14 days (the feedback row links to the notification that carried it)."""
    since = now.astimezone(timezone.utc).replace(tzinfo=None) - timedelta(days=14)
    rows = (
        db.query(models.NotificationFeedback, models.Notification)
        .join(models.Notification, models.Notification.id == models.NotificationFeedback.notification_id)
        .filter(models.NotificationFeedback.user_id == int(user_id), models.NotificationFeedback.created_at >= since)
        .all()
    )
    likes = dislikes = 0
    for fb, notif in rows:
        if notif.template_key != f"plan_motivation_{kind}":
            continue
        if fb.action in ("like", "open_chat"):  # talking to Sedi is the positive reaction (R-039: no Like button)
            likes += 1
        elif fb.action in ("dislike", "dismissed"):
            dislikes += 1
    return {"likes": likes, "dislikes": dislikes}


def _already_sent_recently(db: Session, user_id: int, kind: str, now: datetime, days: int) -> bool:
    since = now.astimezone(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    return (
        db.query(models.Notification.id)
        .filter(
            models.Notification.user_id == int(user_id),
            models.Notification.created_at >= since,
            models.Notification.template_key == f"plan_motivation_{kind}",
        )
        .first()
        is not None
    )


def _local_hhmm(local_now: datetime) -> str:
    return local_now.strftime("%H:%M")


def _in_window(local_now: datetime, hhmm: str) -> bool:
    hh, mm = (int(x) for x in hhmm.split(":"))
    start = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return start <= local_now <= start + timedelta(hours=WINDOW_HOURS)


def _payload(uid: int, kind: str, lang: str, body: str, key: str, extra: dict) -> NotificationPayload:
    return NotificationPayload(
        user_id=uid,
        type="connection_ping",
        title=_TITLE[lang][kind],
        body=body,
        priority="normal",
        dedupe_key=key,
        metadata={"alert_code": ALERT_CODE, "kind": kind, "action_domain": "exercise", **extra},
        category=NotificationCategory.CARE_FOLLOW_UP.value,
        source_type=NotificationSourceType.USER_GOAL.value,
        source_id=f"motivation:{kind}",
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key=f"plan_motivation_{kind}",
        context=sanitize_notification_context(
            {"template_key": f"plan_motivation_{kind}", "trigger_reason": ALERT_CODE, "action_hint": "exercise"}
        ),
        privacy_class="PRIVATE",
    )


def _today_workout(db: Session, uid: int, today_iso: str):
    """The first still-open composer workout of today (title, local_time, minutes) or None."""
    from backend.app.services.i8.action_review import review_of
    from backend.app.services.i8.plan_composer import SOURCE_TAG

    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == uid,
            models.I8OperationalPlanAction.action_domain == "exercise",
            models.I8OperationalPlanAction.status == "ACTIVE",
        )
        .order_by(models.I8OperationalPlanAction.id.desc())
        .limit(80)
        .all()
    )
    found = []
    for a in rows:
        try:
            pres = json.loads(a.presentation_json or "{}")
        except (TypeError, ValueError):
            continue
        if pres.get("source") != SOURCE_TAG or str(pres.get("local_date")) != today_iso or not pres.get("local_time"):
            continue
        if review_of(a):
            continue
        found.append(((a.summary_text or "").strip(), str(pres["local_time"]), pres.get("duration_minutes")))
    return sorted(found, key=lambda x: x[1])[0] if found else None


def process_motivation(db: Session, *, now_utc: Optional[datetime] = None, force: bool = False, limit: int = 300) -> int:
    """Send the motivation notifications that are due. Returns how many were enqueued."""
    if not force and not motivation_enabled():
        return 0
    from zoneinfo import ZoneInfo

    from backend.app.services.i10.plan_progress import feedback_state
    from backend.app.services.i8.local_day import local_today_for_user
    from backend.app.services.i8 import plan_stats as st

    when = now_utc or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    ids = [
        int(r[0])
        for r in db.query(models.I8OperationalPlanAction.user_id)
        .filter(models.I8OperationalPlanAction.status == "ACTIVE", models.I8OperationalPlanAction.action_domain == "exercise")
        .distinct()
        .limit(limit)
        .all()
    ]
    sent = 0
    for uid in ids:
        try:
            tz_name, today = local_today_for_user(db, uid, now_utc=when)
            local_now = when.astimezone(ZoneInfo(tz_name))
            row = db.query(models.User.preferred_language).filter(models.User.id == uid).first()
            lang = ((row[0] if row and row[0] else "fa") or "fa").strip().lower().split("-")[0]
            lang = lang if lang in ("fa", "en", "ar") else "en"
            fb = feedback_state(db, uid, when)
            progress = st.build_progress(db, uid, "exercise", language=lang, now_utc=when)
            if progress.get("state") not in ("active", "review_due") or not progress.get("week_total"):
                continue
            send_at = SHIFTED_LOCAL_TIME if fb["shift_time"] else DEFAULT_LOCAL_TIME
            name = st._name(db, uid)
            style = "short" if fb["simple"] else "normal"
            today_iso = today.isoformat()
            candidates: list[tuple[str, str, dict, str]] = []

            # milestone: celebrate the moment it is reached, once per value (any time of day inside the send window)
            sessions, streak = int(progress["total_done"]), int(progress["streak_weeks"])
            if sessions in st.MILESTONE_SESSIONS:
                candidates.append(("milestone", f"s{sessions}", {"sessions": sessions}, st.milestone_line(lang, name, sessions=sessions)))
            elif streak in st.MILESTONE_STREAK_WEEKS:
                candidates.append(("milestone", f"w{streak}", {"streak_weeks": streak}, st.milestone_line(lang, name, streak_weeks=streak)))

            if progress.get("comeback"):
                react = kind_reaction_state(db, uid, "comeback", when)
                gap = 7 if react["dislikes"] >= 2 and react["likes"] == 0 else 4  # softer after dislikes, never off
                if not _already_sent_recently(db, uid, "comeback", when, gap):
                    candidates.append(("comeback", today_iso, {}, progress["message"]))
            else:
                workout = _today_workout(db, uid, today_iso)
                if workout is not None:
                    react = kind_reaction_state(db, uid, "workout_day", when)
                    gap = 1 if react["likes"] >= 2 else (3 if react["dislikes"] >= 2 else 2)  # every day / every 3rd / every 2nd
                    title, hhmm, minutes = workout
                    if not _already_sent_recently(db, uid, "workout_day", when, gap) and _local_hhmm(local_now) < hhmm:
                        if fb["avoid_generic"]:
                            body = st.practical_line(lang, title, hhmm, int(minutes) if minutes else None)
                        else:
                            body = st.motivation_line(
                                lang,
                                name,
                                week_done=int(progress["week_done"]),
                                week_total=int(progress["week_total"]),
                                seed=f"{uid}:{today_iso}",
                                style=style,
                            )
                        candidates.append(("workout_day", today_iso, {}, body))

            for kind, tag, extra, body in candidates:
                if kind != "milestone" and not _in_window(local_now, send_at):
                    continue
                key = f"i10:self:motivation:{uid}:{kind}:{tag}"
                notif = enqueue_self_scheduler_notification(
                    db,
                    user_id=uid,
                    payload=_payload(uid, kind, lang, body, key, extra),
                    semantic_family=I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP,
                    candidate_key=key,
                    source_type="i8_motivation",
                    source_id=f"{kind}:{tag}",
                )
                if notif is not None:
                    sent += 1
        except Exception:
            db.rollback()
            logger.exception("[I8-motivation] user=%s failed", uid)
    return sent
