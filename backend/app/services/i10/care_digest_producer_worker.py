"""I10-B14 care digest producer — bounded I9 facts → CaregiverNotificationIntent → B06."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.care_subject_status_facts import assemble_care_subject_status_facts
from backend.app.services.i10.caregiver_data_gap import (
    build_care_data_gap_metadata,
    data_gap_occurrence_key_for_facts,
    is_care_data_gap_candidate,
    render_care_data_gap_body,
)
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.caregiver_status_digest import (
    build_care_status_digest_metadata,
    build_care_status_digest_occurrence_key,
    render_care_status_digest_body,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10PrivacyClass, I10SemanticFamily
from backend.app.services.i10.recipient_eligibility import evaluate_recipient_eligibility
from backend.app.services.section10 import feature_flags

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_subject_owner_user_id(db: Session, health_subject_id: int) -> Optional[int]:
    manager = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.access_role == "MANAGER",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .order_by(models.AccountHealthSubjectAccess.id.asc())
        .first()
    )
    if manager is not None:
        return manager.account_user_id
    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .order_by(models.AccountHealthSubjectAccess.id.asc())
        .first()
    )
    return access.account_user_id if access is not None else None


def _authorized_recipients(
    db: Session,
    *,
    health_subject_id: int,
    notification_scope: I10NotificationScope,
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
            notification_scope=notification_scope,
            include_delivery_readiness=False,
        )
        if ev.eligible:
            recipients.append(rid)
    return recipients


def create_care_status_digest_intents_for_subject(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
    commit: bool = True,
) -> list[models.CaregiverNotificationIntent]:
    facts = assemble_care_subject_status_facts(db, health_subject_id=health_subject_id, when=when)
    owner_id = resolve_subject_owner_user_id(db, health_subject_id)
    if owner_id is None:
        return []
    body = render_care_status_digest_body(facts)
    metadata = build_care_status_digest_metadata(facts, body=body)
    occurrence = build_care_status_digest_occurrence_key(
        health_subject_id=health_subject_id,
        period_date=facts.observation_period_start.date(),
    )
    created: list[models.CaregiverNotificationIntent] = []
    for recipient_id in _authorized_recipients(
        db,
        health_subject_id=health_subject_id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    ):
        intent = create_i10_caregiver_delivery_intent(
            db,
            owner_user_id=owner_id,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
            occurrence_key=occurrence,
            semantic_family=I10SemanticFamily.CARE_STATUS_DIGEST,
            privacy_class=I10PrivacyClass.HEALTH_SENSITIVE,
            source_entity_type=metadata["source_entity_type"],
            source_entity_id=None,
            payload_metadata=metadata,
            commit=commit,
        )
        created.append(intent)
    return created


def create_care_data_gap_intents_for_subject(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
    commit: bool = True,
) -> list[models.CaregiverNotificationIntent]:
    facts = assemble_care_subject_status_facts(db, health_subject_id=health_subject_id, when=when)
    if not is_care_data_gap_candidate(facts):
        return []
    owner_id = resolve_subject_owner_user_id(db, health_subject_id)
    if owner_id is None:
        return []
    body = render_care_data_gap_body(facts)
    metadata = build_care_data_gap_metadata(facts, body=body)
    occurrence = data_gap_occurrence_key_for_facts(facts)
    created: list[models.CaregiverNotificationIntent] = []
    for recipient_id in _authorized_recipients(
        db,
        health_subject_id=health_subject_id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    ):
        intent = create_i10_caregiver_delivery_intent(
            db,
            owner_user_id=owner_id,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_id,
            notification_scope=I10NotificationScope.DEVICE_STATUS,
            occurrence_key=occurrence,
            semantic_family=I10SemanticFamily.CARE_DATA_GAP,
            privacy_class=I10PrivacyClass.HEALTH_SENSITIVE,
            source_entity_type=metadata["source_entity_type"],
            source_entity_id=None,
            payload_metadata=metadata,
            commit=commit,
        )
        created.append(intent)
    return created


def run_care_digest_producer_for_subject(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
    deliver: bool = False,
    commit: bool = True,
) -> dict:
    """Produce caregiver status digest and data-gap intents for one subject."""
    if not feature_flags.i10_care_digest_producer_enabled():
        return {"status": "dormant", "status_intents": 0, "gap_intents": 0}

    status_intents = create_care_status_digest_intents_for_subject(
        db, health_subject_id=health_subject_id, when=when, commit=commit
    )
    gap_intents = create_care_data_gap_intents_for_subject(
        db, health_subject_id=health_subject_id, when=when, commit=commit
    )
    delivered = 0
    if deliver and feature_flags.i10_care_network_delivery_enabled():
        for intent in status_intents + gap_intents:
            if intent.status != "pending":
                continue
            outcome = process_caregiver_delivery_intent(db, intent, commit=commit)
            if outcome.get("status") == "processed":
                delivered += 1
    return {
        "status": "ok",
        "status_intents": len(status_intents),
        "gap_intents": len(gap_intents),
        "delivered": delivered,
    }


def run_care_digest_producer_scan(
    db: Session,
    *,
    when: Optional[datetime] = None,
    limit: int = 100,
    deliver: bool = False,
) -> dict:
    """Scan active managed subjects with caregiver access."""
    if not feature_flags.i10_care_digest_producer_enabled():
        return {"processed": 0, "dormant": True}

    rows = (
        db.query(models.HealthSubject.id)
        .join(
            models.AccountHealthSubjectAccess,
            models.AccountHealthSubjectAccess.health_subject_id == models.HealthSubject.id,
        )
        .filter(
            models.HealthSubject.status == "active",
            models.AccountHealthSubjectAccess.access_role == "CAREGIVER",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .distinct()
        .order_by(models.HealthSubject.id.asc())
        .limit(limit)
        .all()
    )
    summary = {"processed": 0, "status_intents": 0, "gap_intents": 0, "delivered": 0}
    for (subject_id,) in rows:
        outcome = run_care_digest_producer_for_subject(
            db, health_subject_id=int(subject_id), when=when, deliver=deliver, commit=True
        )
        summary["processed"] += 1
        summary["status_intents"] += outcome.get("status_intents", 0)
        summary["gap_intents"] += outcome.get("gap_intents", 0)
        summary["delivered"] += outcome.get("delivered", 0)
    return summary
