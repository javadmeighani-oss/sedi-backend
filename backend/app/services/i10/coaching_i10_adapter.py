"""I10-B13 coaching follow-up adapter — persisted I8OperationalPlanAction only."""

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
from backend.app.services.i10.coaching_followup_types import CoachingPlanDomain, resolve_coaching_domain
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

COACHING_PRODUCER_OWNER = "I10_COACHING_FOLLOWUP"


def build_coaching_occurrence_key(*, action_id: int, valid_from_iso: str) -> str:
    return f"i10:self:coaching:{action_id}:{valid_from_iso}"


def resolve_semantic_family(domain: CoachingPlanDomain) -> I10SemanticFamily:
    if domain is CoachingPlanDomain.NUTRITION:
        return I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP
    if domain is CoachingPlanDomain.EXERCISE:
        return I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP
    return I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING


def resolve_privacy_class(domain: CoachingPlanDomain) -> I10PrivacyClass:
    if domain in (CoachingPlanDomain.NUTRITION, CoachingPlanDomain.EXERCISE):
        return I10PrivacyClass.HEALTH_SENSITIVE
    return I10PrivacyClass.PRIVATE


def _safe_user_name(db: Session, user_id: int) -> Optional[str]:
    row = db.query(models.User.name).filter(models.User.id == user_id).first()
    if not row or not row[0]:
        return None
    return str(row[0]).strip()[:64] or None


def render_coaching_copy(
    db: Session,
    action: models.I8OperationalPlanAction,
    *,
    domain: CoachingPlanDomain,
) -> tuple[str, str, str]:
    """Bounded factual copy from persisted plan action — no invented plan content."""
    name = _safe_user_name(db, action.user_id)
    prefix = f"{name}, " if name else ""
    summary = (action.summary_text or "your plan item").strip()[:200]

    if domain is CoachingPlanDomain.NUTRITION:
        title = "Nutrition plan follow-up"
        body = (
            f"{prefix}a meal item registered in today's plan is due: "
            f"'{summary}'. Was it completed?"
        )
        template_key = "nutrition_plan_follow_up"
    elif domain is CoachingPlanDomain.EXERCISE:
        title = "Exercise plan follow-up"
        body = (
            f"{prefix}an exercise item registered in today's plan is due: "
            f"'{summary}'. Was it completed?"
        )
        template_key = "exercise_plan_follow_up"
    else:
        title = "Routine coaching"
        body = (
            f"{prefix}this routine item is registered in your plan for now: "
            f"'{summary}'. Do you have time for it?"
        )
        template_key = "lifestyle_routine_coaching"

    return title, body, template_key


def build_coaching_payload(
    db: Session,
    action: models.I8OperationalPlanAction,
    *,
    domain: CoachingPlanDomain,
    occurrence_key: str,
    i7_continuity_available: bool = False,
) -> NotificationPayload:
    title, body, template_key = render_coaching_copy(db, action, domain=domain)
    notif_type = "health_alert" if domain != CoachingPlanDomain.LIFESTYLE else "connection_ping"
    context = sanitize_notification_context(
        {
            "template_key": template_key,
            "trigger_reason": "i8_plan_coaching_follow_up",
            "source_summary_key": f"i8_action:{action.id}",
            "action_hint": domain.value,
        }
    )
    valid_from_iso = action.valid_from.isoformat() if action.valid_from else "unknown"
    return NotificationPayload(
        user_id=action.user_id,
        type=notif_type,
        title=title,
        body=body,
        priority="normal",
        dedupe_key=occurrence_key,
        metadata={
            "alert_code": "i8_plan_coaching_follow_up",
            "i8_action_id": action.id,
            "i8_plan_id": action.plan_id,
            "action_domain": action.action_domain,
            "coaching_domain": domain.value,
            "i7_continuity_available": i7_continuity_available,
            "plan_item_summary": (action.summary_text or "")[:120],
        },
        category=NotificationCategory.CARE_FOLLOW_UP.value,
        source_type=NotificationSourceType.USER_GOAL.value,
        source_id=str(action.id),
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key=template_key,
        context=context,
        privacy_class=resolve_privacy_class(domain).value,
    )


def enqueue_coaching_followup_notification(
    db: Session,
    *,
    action: models.I8OperationalPlanAction,
    i7_continuity_available: bool = False,
) -> Optional[models.Notification]:
    domain = resolve_coaching_domain(action.action_domain)
    if domain is None:
        return None
    valid_from_iso = action.valid_from.isoformat() if action.valid_from else str(action.id)
    occurrence_key = build_coaching_occurrence_key(action_id=int(action.id), valid_from_iso=valid_from_iso)
    health_subject_id = resolve_or_ensure_self_health_subject_id(db, action.user_id)
    payload = build_coaching_payload(
        db,
        action,
        domain=domain,
        occurrence_key=occurrence_key,
        i7_continuity_available=i7_continuity_available,
    )
    semantic = resolve_semantic_family(domain)
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=action.user_id,
        notification_scope=I10NotificationScope.CARE_ACTION,
        source_owner=COACHING_PRODUCER_OWNER,
        source_type="i8_coaching_followup_worker",
        source_id=str(action.id),
        semantic_family=semantic,
        privacy_hint=resolve_privacy_class(domain),
        provenance_refs=(
            f"i8_operational_plan_action:{action.id}",
            f"i8_operational_plan:{action.plan_id}",
        ),
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B13] suppressed user=%s action=%s reason=%s",
            action.user_id,
            action.id,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
