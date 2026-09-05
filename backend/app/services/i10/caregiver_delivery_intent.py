"""I10 care network delivery intent — extends Section10 intent foundation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.policy_types import I10NotificationScope, I10PrivacyClass, I10SemanticFamily
from backend.app.services.i10.recipient_eligibility import SCOPE_TO_SEMANTIC
from backend.app.services.section10 import feature_flags


def build_i10_occurrence_dedupe_key(
    *,
    health_subject_id: int,
    recipient_user_id: int,
    occurrence_key: str,
    notification_scope: I10NotificationScope,
) -> str:
    return (
        f"i10:care:{health_subject_id}:{recipient_user_id}:"
        f"{occurrence_key}:{notification_scope.value}"
    )


def create_i10_caregiver_delivery_intent(
    db: Session,
    *,
    owner_user_id: Optional[int],
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    occurrence_key: str,
    semantic_family: Optional[I10SemanticFamily] = None,
    privacy_class: I10PrivacyClass = I10PrivacyClass.PRIVATE,
    user_caregiver_id: Optional[int] = None,
    source_entity_type: Optional[str] = None,
    source_entity_id: Optional[int] = None,
    payload_metadata: Optional[dict[str, Any]] = None,
    expires_at: Optional[datetime] = None,
    commit: bool = True,
) -> models.CaregiverNotificationIntent:
    dedupe_key = build_i10_occurrence_dedupe_key(
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        occurrence_key=occurrence_key,
        notification_scope=notification_scope,
    )
    existing = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.dedupe_key == dedupe_key)
        .first()
    )
    if existing is not None:
        return existing

    family = semantic_family or SCOPE_TO_SEMANTIC.get(notification_scope, I10SemanticFamily.GENERAL_STATUS)
    status = "suppressed"
    if feature_flags.i10_care_network_delivery_enabled():
        status = "pending"

    row = models.CaregiverNotificationIntent(
        owner_user_id=owner_user_id,
        caregiver_id=user_caregiver_id,
        notification_type="i10_care_network",
        source_entity_type=source_entity_type or "i10_care_network",
        source_entity_id=source_entity_id,
        status=status,
        dedupe_key=dedupe_key,
        payload_metadata_json=json.dumps(payload_metadata or {}, ensure_ascii=False)[:2000],
        health_subject_id=health_subject_id,
        notification_scope=notification_scope.value,
        occurrence_key=occurrence_key,
        semantic_family=family.value,
        privacy_class=privacy_class.value,
        recipient_user_id=recipient_user_id,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
