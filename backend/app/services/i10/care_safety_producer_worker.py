"""I10-B16 authoritative I4/Section-10 escalation → CaregiverNotificationIntent → B06."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.authorization import get_active_notification_grant
from backend.app.services.i10.care_digest_producer_worker import resolve_subject_owner_user_id
from backend.app.services.i10.care_safety_copy import (
    build_care_safety_metadata,
    build_care_safety_occurrence_key,
    render_care_safety_body,
)
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.i4_escalation_authority import (
    is_authoritative_care_safety_escalation,
    list_authoritative_escalations_for_subject,
    resolve_escalation_health_subject_id,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10PrivacyClass, I10SemanticFamily
from backend.app.services.i10.recipient_eligibility import evaluate_recipient_eligibility
from backend.app.services.section10 import feature_flags

logger = logging.getLogger(__name__)


def _authorized_safety_recipients(
    db: Session,
    *,
    health_subject_id: int,
) -> list[int]:
    accesses = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
            models.AccountHealthSubjectAccess.access_role.in_(("CAREGIVER", "MANAGER")),
        )
        .order_by(models.AccountHealthSubjectAccess.account_user_id.asc())
        .all()
    )
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    recipients: list[int] = []
    seen: set[int] = set()
    for access in accesses:
        rid = access.account_user_id
        if rid in seen:
            continue
        seen.add(rid)
        if subject is not None and subject.linked_user_id == rid:
            continue
        ev = evaluate_recipient_eligibility(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=rid,
            notification_scope=I10NotificationScope.SAFETY_ESCALATION,
            include_delivery_readiness=False,
        )
        if ev.eligible:
            recipients.append(rid)
    return recipients


def _recipient_allows_bounded_detail(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
) -> bool:
    grant = get_active_notification_grant(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
    )
    return grant is not None


def create_care_safety_intents_for_occurrence(
    db: Session,
    *,
    record: models.EmergencyEscalationRecord,
    health_subject_id: int,
    commit: bool = True,
) -> list[models.CaregiverNotificationIntent]:
    if not is_authoritative_care_safety_escalation(record):
        return []
    bound = resolve_escalation_health_subject_id(db, record)
    if bound != health_subject_id:
        return []

    owner_id = resolve_subject_owner_user_id(db, health_subject_id)
    if owner_id is None:
        return []

    occurrence = build_care_safety_occurrence_key(
        health_subject_id=health_subject_id,
        escalation_id=int(record.id),
    )
    created: list[models.CaregiverNotificationIntent] = []
    for recipient_id in _authorized_safety_recipients(db, health_subject_id=health_subject_id):
        include_detail = _recipient_allows_bounded_detail(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_id,
        )
        body = render_care_safety_body(record, include_bounded_detail=include_detail)
        metadata = build_care_safety_metadata(
            record,
            health_subject_id=health_subject_id,
            body=body,
            include_bounded_detail=include_detail,
        )
        intent = create_i10_caregiver_delivery_intent(
            db,
            owner_user_id=owner_id,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_id,
            notification_scope=I10NotificationScope.SAFETY_ESCALATION,
            occurrence_key=occurrence,
            semantic_family=I10SemanticFamily.CARE_SAFETY_ESCALATION,
            privacy_class=I10PrivacyClass.HEALTH_SENSITIVE,
            source_entity_type=metadata["source_entity_type"],
            source_entity_id=int(record.id),
            payload_metadata=metadata,
            commit=commit,
        )
        created.append(intent)
    return created


def run_care_safety_producer_for_subject(
    db: Session,
    *,
    health_subject_id: int,
    deliver: bool = False,
    commit: bool = True,
) -> dict:
    if not feature_flags.i10_care_safety_producer_enabled():
        return {"status": "dormant", "escalations": 0, "intents": 0}

    escalations = list_authoritative_escalations_for_subject(db, health_subject_id=health_subject_id)
    intents: list[models.CaregiverNotificationIntent] = []
    for record in escalations:
        intents.extend(
            create_care_safety_intents_for_occurrence(
                db,
                record=record,
                health_subject_id=health_subject_id,
                commit=commit,
            )
        )
    delivered = 0
    if deliver and feature_flags.i10_care_network_delivery_enabled():
        for intent in intents:
            if intent.status != "pending":
                continue
            outcome = process_caregiver_delivery_intent(db, intent, commit=commit)
            if outcome.get("status") == "processed":
                delivered += 1
    return {
        "status": "ok",
        "escalations": len(escalations),
        "intents": len(intents),
        "delivered": delivered,
    }


def bind_escalation_health_subject_metadata(
    db: Session,
    record: models.EmergencyEscalationRecord,
    *,
    health_subject_id: int,
    commit: bool = True,
) -> models.EmergencyEscalationRecord:
    """Adapter helper — store authoritative HealthSubject binding in existing metadata_json."""
    meta = {}
    if record.metadata_json:
        try:
            loaded = json.loads(record.metadata_json)
            if isinstance(loaded, dict):
                meta = loaded
        except (json.JSONDecodeError, TypeError):
            meta = {}
    meta["health_subject_id"] = health_subject_id
    record.metadata_json = json.dumps(meta, ensure_ascii=False)
    if commit:
        db.commit()
        db.refresh(record)
    else:
        db.flush()
    return record
