"""Caregiver notification intent creation — delivery suppressed unless flags enabled."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags
from backend.app.services.section10.caregiver_notification_resolver import (
    build_dedupe_key,
    resolve_eligible_caregivers,
)


def create_caregiver_notification_intent(
    db: Session,
    *,
    owner_user_id: int,
    caregiver_id: int,
    notification_type: str,
    source_entity_type: Optional[str] = None,
    source_entity_id: Optional[int] = None,
    payload_metadata: Optional[Dict[str, Any]] = None,
    dedupe_bucket: str,
    scheduled_at: Optional[datetime] = None,
) -> Optional[models.CaregiverNotificationIntent]:
    dedupe_key = build_dedupe_key(
        owner_user_id,
        caregiver_id,
        notification_type,
        source_entity_type,
        source_entity_id,
        dedupe_bucket,
    )
    existing = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.dedupe_key == dedupe_key)
        .first()
    )
    if existing is not None:
        return existing

    status = "suppressed"
    if feature_flags.caregiver_delivery_enabled():
        type_flag_map = {
            "daily_health_status": feature_flags.caregiver_daily_report_enabled(),
            "care_summary": feature_flags.caregiver_care_summary_enabled(),
            "important_vital_alert": feature_flags.caregiver_vital_alert_enabled(),
            "emergency_escalation": feature_flags.caregiver_delivery_enabled(),
        }
        if type_flag_map.get(notification_type, False):
            status = "pending"

    row = models.CaregiverNotificationIntent(
        owner_user_id=owner_user_id,
        caregiver_id=caregiver_id,
        notification_type=notification_type,
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        status=status,
        dedupe_key=dedupe_key,
        payload_metadata_json=json.dumps(payload_metadata or {}, ensure_ascii=False)[:2000],
        scheduled_at=scheduled_at,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def enqueue_for_eligible_caregivers(
    db: Session,
    owner_user_id: int,
    notification_type: str,
    *,
    source_entity_type: Optional[str] = None,
    source_entity_id: Optional[int] = None,
    payload_metadata: Optional[Dict[str, Any]] = None,
    dedupe_bucket: str,
) -> list:
    caregivers = resolve_eligible_caregivers(db, owner_user_id, notification_type)
    created = []
    for cg in caregivers:
        intent = create_caregiver_notification_intent(
            db,
            owner_user_id=owner_user_id,
            caregiver_id=cg.id,
            notification_type=notification_type,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            payload_metadata=payload_metadata,
            dedupe_bucket=dedupe_bucket,
        )
        if intent is not None:
            created.append(intent.id)
    return created
