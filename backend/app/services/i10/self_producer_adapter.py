"""I10 adapter for active SELF scheduler producers (B08) — legacy semantics, canonical intake."""

from __future__ import annotations

import logging
from datetime import datetime
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
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account

logger = logging.getLogger(__name__)

SELF_PRODUCER_OWNER = "I10_SELF_LEGACY_ADAPTER"


def resolve_self_health_subject_id(db: Session, account_user_id: int) -> Optional[int]:
    """Return the linked SELF HealthSubject id for an account when one exists."""
    row = (
        db.query(models.HealthSubject.id)
        .join(
            models.AccountHealthSubjectAccess,
            models.AccountHealthSubjectAccess.health_subject_id == models.HealthSubject.id,
        )
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.access_role == "SELF",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
            models.HealthSubject.linked_user_id == account_user_id,
            models.HealthSubject.status == "active",
        )
        .order_by(models.HealthSubject.id.asc())
        .first()
    )
    return int(row[0]) if row else None


def resolve_or_ensure_self_health_subject_id(db: Session, account_user_id: int) -> int:
    """Canonical SELF subject attribution — uses I9 ensure helper, never managed-subject substitution."""
    existing = resolve_self_health_subject_id(db, account_user_id)
    if existing is not None:
        return existing
    subject = ensure_self_subject_for_account(db, account_user_id, commit=True)
    return int(subject.id)


def build_self_occurrence_key(
    producer: str,
    *,
    user_id: int,
    scheduled_for: datetime,
    bucket: Optional[int] = None,
    extra: Optional[str] = None,
) -> str:
    """Stable per-occurrence identity aligned with legacy dedupe windows."""
    date_str = scheduled_for.strftime("%Y-%m-%d")
    if producer == "morning":
        return f"i10:self:morning:{user_id}:{date_str}"
    if producer == "inactivity":
        hour_bucket = bucket if bucket is not None else (scheduled_for.hour // 4) * 4
        return f"i10:self:inactivity:{user_id}:{date_str}:{hour_bucket:02d}"
    if producer == "engagement":
        hour_bucket = bucket if bucket is not None else (scheduled_for.hour // 3) * 3
        return f"i10:self:engagement:{user_id}:{date_str}:{hour_bucket:02d}"
    if producer == "companion":
        return f"i10:self:companion:{user_id}:{date_str}"
    if producer == "device_disconnected":
        device_id = extra or "unknown"
        hour_bucket = bucket if bucket is not None else (scheduled_for.hour // 6) * 6
        return f"i10:self:device_disconnected:{user_id}:{device_id}:{date_str}:{hour_bucket:02d}"
    if producer == "health_alert":
        alert_code = extra or "generic"
        hour_str = scheduled_for.strftime("%H")
        return f"i10:self:health_alert:{user_id}:{alert_code}:{date_str}T{hour_str}"
    if producer == "user_chat_reminder":
        return f"i10:self:user_chat_reminder:{user_id}:{extra or date_str}"
    raise ValueError(f"I10_SELF_UNKNOWN_PRODUCER:{producer}")


def enqueue_self_scheduler_notification(
    db: Session,
    *,
    user_id: int,
    payload: NotificationPayload,
    semantic_family: I10SemanticFamily,
    candidate_key: str,
    source_type: str,
    source_id: str,
    notification_scope: I10NotificationScope = I10NotificationScope.GENERAL_STATUS,
    privacy_class: I10PrivacyClass = I10PrivacyClass.PUBLIC_SAFE,
) -> Optional[models.Notification]:
    """Route a prepared SELF scheduler payload through canonical I10 intake."""
    health_subject_id = resolve_or_ensure_self_health_subject_id(db, user_id)
    payload = payload.model_copy(update={"dedupe_key": candidate_key})
    candidate = I10NotificationCandidate(
        candidate_key=candidate_key,
        health_subject_id=health_subject_id,
        recipient_user_id=user_id,
        notification_scope=notification_scope,
        source_owner=SELF_PRODUCER_OWNER,
        source_type=source_type,
        source_id=source_id,
        semantic_family=semantic_family,
        privacy_hint=privacy_class,
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B08] suppressed user=%s candidate=%s reason=%s",
            user_id,
            candidate_key,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
