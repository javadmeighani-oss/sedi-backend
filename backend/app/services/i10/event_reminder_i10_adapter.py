"""I10 adapter for SELF event reminders (B10 medical + R-026 generic) — UserEvent authority preserved."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import pytz

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    sanitize_notification_context,
)
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i10.self_producer_adapter import resolve_or_ensure_self_health_subject_id

logger = logging.getLogger(__name__)

EVENT_PRODUCER_OWNER = "I10_EVENT_REMINDER_ADAPTER"

DOCTOR_EVENT_TYPE = "doctor_visit"
LAB_EVENT_TYPE = "lab_test"

MEDICAL_EVENT_TYPES = frozenset({
    DOCTOR_EVENT_TYPE,
    LAB_EVENT_TYPE,
    "medical_follow_up",
    "imaging",
    "surgery",
    "care_followup",
})

REMINDER_STAGE_UPCOMING = "upcoming"


def build_event_occurrence_key(
    *, user_id: int, event_id: int, offset_min: int, occurrence_day: Optional[str] = None
) -> str:
    """Unique per reminder; a repeating event adds the occurrence's local day (YYYYMMDD) so every day dedupes alone."""
    base = f"i10:event:{user_id}:{event_id}:{offset_min}"
    return f"{base}:{occurrence_day}" if occurrence_day else base


GENERIC_EVENT_TYPES = frozenset({
    "exam",
    "deadline",
    "work_meeting",
    "birthday",
    "important_day",
    "other",
})

GENERIC_EVENT_DOMAINS = frozenset({
    "personal",
    "work",
    "education",
    "lifestyle",
    "family",
    "other",
})


def is_medical_remindable_event(event: models.UserEvent) -> bool:
    return event.event_type in MEDICAL_EVENT_TYPES or event.event_domain in {"medical", "care"}


def is_generic_remindable_event(event: models.UserEvent) -> bool:
    """Non-medical UserEvent reminder eligibility (schema-free adapter)."""
    if is_medical_remindable_event(event):
        return False
    if event.event_type in GENERIC_EVENT_TYPES:
        return True
    return event.event_domain in GENERIC_EVENT_DOMAINS


def is_remindable_event(event: models.UserEvent) -> bool:
    return is_medical_remindable_event(event) or is_generic_remindable_event(event)


def resolve_event_semantic_family(event_type: str, *, medical: bool = True) -> I10SemanticFamily:
    if not medical:
        return I10SemanticFamily.REMINDER
    if event_type == DOCTOR_EVENT_TYPE:
        return I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER
    if event_type == LAB_EVENT_TYPE:
        return I10SemanticFamily.LAB_APPOINTMENT_REMINDER
    return I10SemanticFamily.MEDICAL_EVENT_REMINDER


REMINDER_EXPIRY_GRACE_MINUTES = 30
_TITLES = {
    "fa": "یادآوری از صدی",
    "ar": "تذكير من صدی",
    "en": "Reminder from Sedi",
}


def event_starts_utc(event: models.UserEvent) -> Optional[datetime]:
    """UserEvent.starts_at (naive, in the event's own timezone) -> naive UTC."""
    starts = event.starts_at
    if starts is None:
        return None
    try:
        tz = pytz.timezone(event.timezone or "Asia/Tehran")
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Asia/Tehran")
    if starts.tzinfo is None:
        starts = tz.localize(starts)
    return starts.astimezone(pytz.UTC).replace(tzinfo=None)


def _user_language(db: Optional[Session], user_id: int) -> str:
    if db is None:
        return "en"
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        lang = (getattr(user, "preferred_language", None) or "").strip().lower()
    except Exception:
        lang = ""
    return lang if lang in ("fa", "ar", "en") else "en"


def _lead_phrase(offset_min: int, lang: str) -> str:
    """How far ahead the event is: "الان" / "یه ساعت دیگه" / "in 15 minutes"."""
    if offset_min <= 0:
        return {"fa": "الان", "ar": "الآن", "en": "Now"}[lang]
    if lang == "fa":
        digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        if offset_min % 1440 == 0:
            n = offset_min // 1440
            return "فردا" if n == 1 else f"{n} روز دیگه".translate(digits)
        if offset_min % 60 == 0:
            n = offset_min // 60
            return "یه ساعت دیگه" if n == 1 else f"{n} ساعت دیگه".translate(digits)
        return f"{offset_min} دقیقه دیگه".translate(digits)
    if lang == "ar":
        if offset_min % 1440 == 0:
            n = offset_min // 1440
            return "غداً" if n == 1 else f"بعد {n} أيام"
        if offset_min % 60 == 0:
            n = offset_min // 60
            return "بعد ساعة" if n == 1 else f"بعد {n} ساعات"
        return f"بعد {offset_min} دقيقة"
    if offset_min % 1440 == 0:
        n = offset_min // 1440
        return "Tomorrow" if n == 1 else f"In {n} days"
    if offset_min % 60 == 0:
        n = offset_min // 60
        return "In 1 hour" if n == 1 else f"In {n} hours"
    return f"In {offset_min} minutes"


def _reminder_copy(
    event: models.UserEvent,
    *,
    medical: bool,
    lang: str = "en",
    offset_min: int = 0,
) -> Tuple[str, str, str]:
    """Warm, localized reminder copy (R-011/R-026).

    Lock-screen safe: medical reminders never repeat the user's own title; generic ones show the user's own
    reminder text because they asked for exactly that text.
    """
    lang = lang if lang in _TITLES else "en"
    title = _TITLES[lang]
    lead = _lead_phrase(offset_min, lang)
    if not medical:
        label = (event.title or "").strip()
        if lang == "fa":
            body = f"{lead} وقتِ «{label}»ه 🌿" if label else f"{lead} وقت یادآوری‌ته 🌿"
        elif lang == "ar":
            body = f"{lead} موعد «{label}» 🌿" if label else f"{lead} موعد تذكيرك 🌿"
        else:
            body = f"{lead}: {label} 🌿" if label else f"{lead} it's time for your reminder 🌿"
        return title, body, "generic_event_reminder"
    if event.event_type == DOCTOR_EVENT_TYPE:
        template_key = "doctor_appointment_reminder"
        body = {
            "fa": f"{lead} وقت نوبت دکترته 🌿",
            "ar": f"{lead} موعد زيارة طبيبك 🌿",
            "en": f"{lead}: your doctor visit 🌿",
        }[lang]
    elif event.event_type == LAB_EVENT_TYPE:
        template_key = "lab_appointment_reminder"
        body = {
            "fa": f"{lead} وقت آزمایشته 🌿",
            "ar": f"{lead} موعد تحليلك 🌿",
            "en": f"{lead}: your lab test 🌿",
        }[lang]
    else:
        template_key = "medical_event_reminder"
        body = {
            "fa": f"{lead} یه برنامه‌ی پزشکی داری 🌿",
            "ar": f"{lead} لديك موعد طبي 🌿",
            "en": f"{lead}: you have a medical event 🌿",
        }[lang]
    return title, body, template_key


def build_event_reminder_payload(
    event: models.UserEvent,
    *,
    user_id: int,
    occurrence_key: str,
    offset_min: int,
    language: str = "en",
) -> NotificationPayload:
    medical = is_medical_remindable_event(event)
    if not medical and not is_generic_remindable_event(event):
        raise ValueError("event is not remindable")
    title, body, template_key = _reminder_copy(
        event, medical=medical, lang=language, offset_min=offset_min
    )
    context = sanitize_notification_context(
        {
            "template_key": template_key,
            "trigger_reason": "event_reminder",
            "schedule_label": f"{offset_min}m_before",
        }
    )
    return NotificationPayload(
        user_id=user_id,
        type="health_alert" if medical else "connection_ping",
        title=title,
        body=body,
        priority="normal",
        dedupe_key=occurrence_key,
        metadata={
            "alert_code": "event_reminder",
            "event_id": event.id,
            "event_type": event.event_type,
            "offset_minutes": offset_min,
            "reminder_stage": REMINDER_STAGE_UPCOMING,
            "post_event_follow_up_eligible": False,
            "language": language,
        },
        category=NotificationCategory.EVENT_REMINDER.value,
        source_type=NotificationSourceType.USER_EVENT.value,
        source_id=str(event.id),
        risk_level=NotificationRiskLevel.NORMAL.value,
        template_key=template_key,
        context=context,
        privacy_class=(
            I10PrivacyClass.HEALTH_SENSITIVE.value if medical else I10PrivacyClass.PRIVATE.value
        ),
    )


def evaluate_post_event_follow_up_eligible(event: models.UserEvent, now: datetime) -> bool:
    """B12 handoff — event ended; follow-up may be scheduled later. Does not assert attendance."""
    if event.status not in ("scheduled", "confirmed", "completed"):
        return False
    end_at = event.ends_at or event.starts_at
    if end_at is None:
        return False
    if end_at.tzinfo is not None:
        end_naive = end_at.replace(tzinfo=None)
    else:
        end_naive = end_at
    return end_naive <= now


def enqueue_event_reminder_notification(
    db: Session,
    *,
    event: models.UserEvent,
    user_id: int,
    occurrence_key: str,
    offset_min: int,
    starts_utc_override: Optional[datetime] = None,
) -> Optional[models.Notification]:
    if not is_remindable_event(event):
        return None
    medical = is_medical_remindable_event(event)
    health_subject_id = resolve_or_ensure_self_health_subject_id(db, user_id)
    language = _user_language(db, user_id)
    payload = build_event_reminder_payload(
        event,
        user_id=user_id,
        occurrence_key=occurrence_key,
        offset_min=offset_min,
        language=language,
    )
    semantic = resolve_event_semantic_family(event.event_type, medical=medical)
    # The UserEvent is the validity authority: the reminder stays deliverable until the event has started
    # (plus a short grace), then expires. Without this the provider freshness gate blocks the send.
    starts_utc = starts_utc_override or event_starts_utc(event)
    now_aware = datetime.now(timezone.utc)
    expires_at = (
        (starts_utc.replace(tzinfo=timezone.utc) + timedelta(minutes=REMINDER_EXPIRY_GRACE_MINUTES))
        if starts_utc
        else None
    )
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=user_id,
        notification_scope=(
            I10NotificationScope.SENSITIVE_HEALTH_DETAIL
            if medical
            else I10NotificationScope.GENERAL_STATUS
        ),
        source_owner=EVENT_PRODUCER_OWNER,
        source_type="event_reminder_scheduler",
        source_id=f"{event.id}:{offset_min}",
        semantic_family=semantic,
        privacy_hint=(
            I10PrivacyClass.HEALTH_SENSITIVE if medical else I10PrivacyClass.PRIVATE
        ),
        provenance_refs=(f"user_event:{event.id}", f"offset_min:{offset_min}"),
        valid_from=now_aware,
        expires_at=expires_at,
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B10] suppressed user=%s event=%s occurrence=%s reason=%s",
            user_id,
            event.id,
            occurrence_key,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
