"""
Gate 4-C — Safe notification context for chat restoration.

Builds an internal-only dict for ConversationBrain. Never returned to clients.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from backend.app.models import Notification
from backend.app.services.gate4.notification_context import (
    resolve_effective_category,
    resolve_effective_risk_level,
    sanitize_notification_context,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i10.recipient_eligibility import evaluate_recipient_eligibility

_MAX_TITLE_CHARS = 200

_SEMANTIC_TO_SCOPE: dict[str, I10NotificationScope] = {
    I10SemanticFamily.CARE_STATUS_DIGEST.value: I10NotificationScope.GENERAL_STATUS,
    I10SemanticFamily.CARE_DATA_GAP.value: I10NotificationScope.DEVICE_STATUS,
    I10SemanticFamily.GENERAL_STATUS.value: I10NotificationScope.GENERAL_STATUS,
    I10SemanticFamily.DEVICE_STATUS.value: I10NotificationScope.DEVICE_STATUS,
}


def _resolve_required_scope(notification: Notification) -> Optional[I10NotificationScope]:
    if notification.semantic_family:
        mapped = _SEMANTIC_TO_SCOPE.get(str(notification.semantic_family))
        if mapped is not None:
            return mapped
    return None


def _caregiver_subject_access_valid(
    db: Session,
    *,
    notification: Notification,
    viewer_user_id: int,
) -> bool:
    if notification.health_subject_id is None:
        return True
    from backend.app import models

    subject_row = (
        db.query(models.HealthSubject)
        .filter(models.HealthSubject.id == notification.health_subject_id)
        .first()
    )
    if subject_row is None:
        return False
    if subject_row.linked_user_id == viewer_user_id:
        return True
    scope = _resolve_required_scope(notification)
    if scope is None:
        return False
    ev = evaluate_recipient_eligibility(
        db,
        health_subject_id=int(notification.health_subject_id),
        recipient_user_id=viewer_user_id,
        notification_scope=scope,
        include_delivery_readiness=False,
    )
    return ev.eligible


def build_revoked_caregiver_chat_context(notification: Notification) -> dict[str, Any]:
    """Fail-closed generic context when caregiver subject access/grant was revoked."""
    return {
        "category": "care_notification",
        "risk_level": "informational",
        "template_key": "care_notification_generic",
        "source_type": notification.source_type or "caregiver_delivery",
        "source_id": str(notification.source_id or notification.id)[:255],
        "notification_title": "Care notification",
        "context_hints": sanitize_notification_context(
            {"subject_context_available": "false"}
        ),
    }


def build_safe_chat_context(
    notification: Notification,
    *,
    db: Optional[Session] = None,
    viewer_user_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Build sanitized notification context for internal GPT prompt injection.

    Never includes notification body, raw context_json, PII, diagnosis, dosage,
    or medication-change data.

    When viewer_user_id and db are supplied for caregiver notifications tied to a
    HealthSubject, access/grant is revalidated at chat time (fail-closed downgrade).
    """
    if db is not None and viewer_user_id is not None and notification.health_subject_id is not None:
        if not _caregiver_subject_access_valid(db, notification=notification, viewer_user_id=viewer_user_id):
            return build_revoked_caregiver_chat_context(notification)

    parsed_context: Optional[Mapping[str, Any]] = None
    if notification.context_json:
        try:
            loaded = json.loads(notification.context_json)
            if isinstance(loaded, dict):
                parsed_context = loaded
        except (json.JSONDecodeError, TypeError):
            parsed_context = None

    context_hints = sanitize_notification_context(parsed_context) or {}

    category = resolve_effective_category(
        category=notification.category,
        notification_type=notification.type or "",
        context_json=notification.context_json,
    )
    risk_level = resolve_effective_risk_level(
        risk_level=notification.risk_level,
        priority=notification.priority or "normal",
    )

    title = (notification.title or "").strip()[:_MAX_TITLE_CHARS]

    result: dict[str, Any] = {
        "category": category,
        "risk_level": risk_level,
    }

    if notification.template_key:
        result["template_key"] = str(notification.template_key)[:100]
    if notification.source_type:
        result["source_type"] = str(notification.source_type)[:64]
    if notification.source_id:
        result["source_id"] = str(notification.source_id)[:255]
    if context_hints:
        result["context_hints"] = context_hints
    if title:
        result["notification_title"] = title

    return result
