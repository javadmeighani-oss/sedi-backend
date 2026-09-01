"""I10-B12 contextual follow-up notification adapter — structured CareFollowUpTask only."""

from __future__ import annotations

import logging
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
from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta
from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource
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

FOLLOWUP_PRODUCER_OWNER = "I10_CONTEXTUAL_FOLLOWUP"


def build_followup_occurrence_key(*, task_id: int) -> str:
    return f"i10:self:followup:{task_id}"


def resolve_semantic_family(task: models.CareFollowUpTask) -> I10SemanticFamily:
    if task.source == FollowUpTaskSource.POST_EVENT.value:
        return I10SemanticFamily.POST_EVENT_FOLLOW_UP
    return I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP


def resolve_privacy_class(task: models.CareFollowUpTask) -> I10PrivacyClass:
    if task.source == FollowUpTaskSource.POST_EVENT.value:
        return I10PrivacyClass.HEALTH_SENSITIVE
    return I10PrivacyClass.PRIVATE


def _safe_user_name(db: Session, user_id: int) -> Optional[str]:
    row = db.query(models.User.name).filter(models.User.id == user_id).first()
    if not row or not row[0]:
        return None
    return str(row[0]).strip()[:64] or None


def render_followup_copy(
    db: Session,
    task: models.CareFollowUpTask,
) -> tuple[str, str, str]:
    """Deterministic bounded copy — no attendance claims, no invented health facts."""
    _user_text, meta = parse_bounded_meta(task.description)
    name = _safe_user_name(db, task.user_id)
    prefix = f"{name}, " if name else ""

    if task.source == FollowUpTaskSource.POST_EVENT.value:
        title = "Follow-up on your appointment"
        body = (
            f"{prefix}how did your appointment go? "
            "If you'd like, we can talk about it."
        )
        template_key = "post_event_follow_up"
    else:
        title = "Continuing our conversation"
        topic = (task.title or "this topic").strip()[:120]
        body = (
            f"{prefix}you asked to continue later about '{topic}'. "
            "Do you have time to talk now?"
        )
        template_key = "contextual_follow_up"

    if meta.follow_up_kind == "general_ctx" and task.source == FollowUpTaskSource.MANUAL.value:
        body = (
            f"{prefix}you asked to follow up later about '{task.title[:120]}'. "
            "Do you have time now?"
        )

    return title, body, template_key


def build_followup_payload(
    db: Session,
    task: models.CareFollowUpTask,
    *,
    occurrence_key: str,
) -> NotificationPayload:
    title, body, template_key = render_followup_copy(db, task)
    _user_text, meta = parse_bounded_meta(task.description)
    context = sanitize_notification_context(
        {
            "template_key": template_key,
            "trigger_reason": "contextual_follow_up",
            "source_summary_key": f"follow_up_task:{task.id}",
            "action_hint": task.source,
        }
    )
    notif_type = "connection_ping"
    if task.source == FollowUpTaskSource.POST_EVENT.value:
        notif_type = "health_alert"
    return NotificationPayload(
        user_id=task.user_id,
        type=notif_type,
        title=title,
        body=body,
        priority="normal",
        dedupe_key=occurrence_key,
        metadata={
            "alert_code": "contextual_follow_up",
            "follow_up_task_id": task.id,
            "follow_up_source": task.source,
            "follow_up_kind": meta.follow_up_kind,
            "user_event_id": meta.user_event_id,
            "prior_source_notification_id": meta.source_notification_id,
        },
        category=NotificationCategory.CARE_FOLLOW_UP.value,
        source_type=NotificationSourceType.CARE_FOLLOW_UP_TASK.value,
        source_id=str(task.id),
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key=template_key,
        context=context,
        privacy_class=resolve_privacy_class(task).value,
    )


def enqueue_contextual_followup_notification(
    db: Session,
    *,
    task: models.CareFollowUpTask,
) -> Optional[models.Notification]:
    occurrence_key = build_followup_occurrence_key(task_id=task.id)
    health_subject_id = resolve_or_ensure_self_health_subject_id(db, task.user_id)
    payload = build_followup_payload(db, task, occurrence_key=occurrence_key)
    semantic = resolve_semantic_family(task)
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=task.user_id,
        notification_scope=I10NotificationScope.CARE_ACTION,
        source_owner=FOLLOWUP_PRODUCER_OWNER,
        source_type="contextual_followup_worker",
        source_id=str(task.id),
        semantic_family=semantic,
        privacy_hint=resolve_privacy_class(task),
        provenance_refs=(f"care_follow_up_task:{task.id}", f"source:{task.source}"),
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B12] suppressed user=%s task=%s reason=%s",
            task.user_id,
            task.id,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
