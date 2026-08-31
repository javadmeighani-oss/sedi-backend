"""I10 adapter for SELF medication reminder notifications (B09)."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
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

MEDICATION_PRODUCER_OWNER = "I10_MEDICATION_LEGACY_ADAPTER"


def enqueue_medication_reminder_notification(
    db: Session,
    *,
    user_id: int,
    payload: NotificationPayload,
    occurrence_key: str,
    user_medication_id: int,
    occurrence_id: int,
) -> Optional[models.Notification]:
    health_subject_id = resolve_or_ensure_self_health_subject_id(db, user_id)
    payload = payload.model_copy(update={"dedupe_key": occurrence_key})
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=user_id,
        notification_scope=I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
        source_owner=MEDICATION_PRODUCER_OWNER,
        source_type="medication_reminders",
        source_id=str(occurrence_id),
        semantic_family=I10SemanticFamily.MEDICATION_DUE,
        privacy_hint=I10PrivacyClass.HEALTH_SENSITIVE,
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B09] suppressed user=%s occurrence=%s reason=%s",
            user_id,
            occurrence_key,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
