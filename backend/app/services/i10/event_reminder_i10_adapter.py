"""I10 adapter for SELF medical event reminders (B10) — UserEvent authority preserved."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Tuple

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


def build_event_occurrence_key(*, user_id: int, event_id: int, offset_min: int) -> str:
    return f"i10:event:{user_id}:{event_id}:{offset_min}"


def resolve_event_semantic_family(event_type: str) -> I10SemanticFamily:
    if event_type == DOCTOR_EVENT_TYPE:
        return I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER
    if event_type == LAB_EVENT_TYPE:
        return I10SemanticFamily.LAB_APPOINTMENT_REMINDER
    return I10SemanticFamily.MEDICAL_EVENT_REMINDER


def _reminder_copy(event: models.UserEvent) -> Tuple[str, str, str]:
    """Type-aware factual reminder copy — no diagnosis, prep instructions, or attendance claims."""
    title = (event.title or "Medical event")[:256]
    if event.event_type == DOCTOR_EVENT_TYPE:
        body = "Your scheduled doctor visit is approaching."
        template_key = "doctor_appointment_reminder"
    elif event.event_type == LAB_EVENT_TYPE:
        body = "Your scheduled lab test is approaching."
        template_key = "lab_appointment_reminder"
    else:
        body = "Your scheduled medical event is approaching."
        template_key = "medical_event_reminder"
    return title, body, template_key


def build_event_reminder_payload(
    event: models.UserEvent,
    *,
    user_id: int,
    occurrence_key: str,
    offset_min: int,
) -> NotificationPayload:
    title, body, template_key = _reminder_copy(event)
    context = sanitize_notification_context(
        {
            "template_key": template_key,
            "trigger_reason": "event_reminder",
            "schedule_label": f"{offset_min}m_before",
        }
    )
    return NotificationPayload(
        user_id=user_id,
        type="health_alert",
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
        },
        category=NotificationCategory.EVENT_REMINDER.value,
        source_type=NotificationSourceType.USER_EVENT.value,
        source_id=str(event.id),
        risk_level=NotificationRiskLevel.NORMAL.value,
        template_key=template_key,
        context=context,
        privacy_class=I10PrivacyClass.HEALTH_SENSITIVE.value,
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
) -> Optional[models.Notification]:
    health_subject_id = resolve_or_ensure_self_health_subject_id(db, user_id)
    payload = build_event_reminder_payload(
        event, user_id=user_id, occurrence_key=occurrence_key, offset_min=offset_min
    )
    semantic = resolve_event_semantic_family(event.event_type)
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=user_id,
        notification_scope=I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
        source_owner=EVENT_PRODUCER_OWNER,
        source_type="event_reminder_scheduler",
        source_id=f"{event.id}:{offset_min}",
        semantic_family=semantic,
        privacy_hint=I10PrivacyClass.HEALTH_SENSITIVE,
        provenance_refs=(f"user_event:{event.id}", f"offset_min:{offset_min}"),
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


def is_medical_remindable_event(event: models.UserEvent) -> bool:
    return event.event_type in MEDICAL_EVENT_TYPES or event.event_domain in {"medical", "care"}
