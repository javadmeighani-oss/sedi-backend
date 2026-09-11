"""I10 DEVICE_STATUS — gadget-reported vital status transitions to caregivers.

DRVS rows remain persisted. I10 minting is suppressed when canonical MAD HR
stability intents already exist for the same subject/day (anti-dupe).
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.care_digest_producer_worker import (
    _authorized_recipients,
    resolve_subject_owner_user_id,
)
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.policy_types import I10NotificationScope, I10PrivacyClass, I10SemanticFamily
from backend.app.services.i9.device_reported_vital_status import (
    STATUS_STABLE,
    STATUS_UNSTABLE,
    EffectiveVitalStatus,
)

logger = logging.getLogger(__name__)

PRODUCER_OWNER = "I10_DEVICE_REPORTED_VITAL_STATUS"
FORBIDDEN_MEANINGS = (
    "safe",
    "healthy",
    "danger",
    "emergency",
    "diagnosis",
    "critical",
    "medically",
)


def render_device_reported_vital_status_body(
    *,
    previous_status: Optional[str],
    new_status: str,
) -> str:
    # Generic subject wording — never hard-code a person label.
    if previous_status is None and new_status == STATUS_STABLE:
        return "Gadget reports the subject's vital-sign status as stable."
    if previous_status is None and new_status == STATUS_UNSTABLE:
        return "Gadget reports the subject's vital-sign status as unstable/changed. Please check on them."
    if previous_status == STATUS_STABLE and new_status == STATUS_UNSTABLE:
        return "Gadget reports the subject's vital-sign status as unstable/changed. Please check on them."
    if previous_status == STATUS_UNSTABLE and new_status == STATUS_STABLE:
        return "Gadget reports the subject's status has returned to stable."
    return f"Gadget reports the subject's vital-sign status as {new_status.lower()}."


def build_device_reported_vital_occurrence_key(
    *,
    health_subject_id: int,
    previous_status: Optional[str],
    new_status: str,
    status_row_id: int,
) -> str:
    prev = previous_status or "NONE"
    return f"i10:drv:{health_subject_id}:transition:{prev}:{new_status}:{status_row_id}"


def should_notify_device_reported_transition(
    *,
    previous: Optional[EffectiveVitalStatus],
    new_effective: Optional[EffectiveVitalStatus],
    ingested_row_id: int,
) -> bool:
    """Notify only when ingested row becomes effective and status changes (incl. first)."""
    if new_effective is None:
        return False
    if int(new_effective.row_id) != int(ingested_row_id):
        return False
    prev_status = previous.status if previous is not None else None
    if prev_status == new_effective.status:
        return False
    return True


def _canonical_hr_i10_already_emitted(db: Session, *, health_subject_id: int, when) -> bool:
    """True when MAD-canonical HR daily/instability intents exist for subject/day."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    day = when.astimezone(timezone.utc).date().isoformat()
    prefix_daily = f"i10:hr:daily_stability:{int(health_subject_id)}:{day}"
    prefix_inst = f"i10:hr:instability:{int(health_subject_id)}:{day}:"
    rows = (
        db.query(models.CaregiverNotificationIntent.occurrence_key)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == int(health_subject_id),
            models.CaregiverNotificationIntent.semantic_family.in_(
                (
                    I10SemanticFamily.HR_DAILY_STABILITY.value,
                    I10SemanticFamily.HR_INSTABILITY.value,
                )
            ),
        )
        .all()
    )
    for (key,) in rows:
        if key == prefix_daily or (key or "").startswith(prefix_inst):
            return True
    return False


def emit_device_reported_vital_status_notifications(
    db: Session,
    *,
    health_subject_id: int,
    ingested_row: models.DeviceReportedVitalStatus,
    previous: Optional[EffectiveVitalStatus],
    new_effective: Optional[EffectiveVitalStatus],
    deliver: bool = False,
    commit: bool = True,
) -> list[models.CaregiverNotificationIntent]:
    if not should_notify_device_reported_transition(
        previous=previous,
        new_effective=new_effective,
        ingested_row_id=int(ingested_row.id),
    ):
        return []

    assert new_effective is not None
    detected = ingested_row.detected_at
    if _canonical_hr_i10_already_emitted(db, health_subject_id=health_subject_id, when=detected):
        logger.info(
            "[I10_DRVS] suppressed_dupe hs=%s row=%s reason=canonical_hr_stability_already_emitted",
            health_subject_id,
            ingested_row.id,
        )
        return []

    prev_status = previous.status if previous is not None else None
    body = render_device_reported_vital_status_body(
        previous_status=prev_status,
        new_status=new_effective.status,
    )
    lower = body.lower()
    for forbidden in ("danger", "emergency", "diagnosis", "critical", "healthy", " medically safe"):
        if forbidden.strip() in lower:
            raise ValueError(f"FORBIDDEN_NOTIFICATION_LANGUAGE:{forbidden.strip()}")

    metadata = {
        "title": "Device-reported vital status",
        "body": body,
        "template_key": "device_reported_vital_status",
        "trigger_reason": "device_reported_vital_status_transition",
        "status": new_effective.status,
        "previous_status": prev_status,
        "source_class": "DEVICE_REPORTED",
        "context": {
            "template_key": "device_reported_vital_status",
            "status": new_effective.status,
            "previous_status": prev_status,
            "source_class": "DEVICE_REPORTED",
            "device_reported_vital_status_id": int(ingested_row.id),
        },
        "semantic_family": I10SemanticFamily.DEVICE_STATUS.value,
        "privacy_class": I10PrivacyClass.HEALTH_SENSITIVE.value,
        "source_entity_type": PRODUCER_OWNER,
        "source_entity_id": int(ingested_row.id),
    }
    occurrence = build_device_reported_vital_occurrence_key(
        health_subject_id=health_subject_id,
        previous_status=prev_status,
        new_status=new_effective.status,
        status_row_id=int(ingested_row.id),
    )
    owner_id = resolve_subject_owner_user_id(db, health_subject_id)
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
            semantic_family=I10SemanticFamily.DEVICE_STATUS,
            privacy_class=I10PrivacyClass.HEALTH_SENSITIVE,
            source_entity_type=PRODUCER_OWNER,
            source_entity_id=int(ingested_row.id),
            payload_metadata=metadata,
            commit=commit,
        )
        created.append(intent)
        if deliver and intent.status == "pending":
            process_caregiver_delivery_intent(db, intent, commit=commit)
    logger.info(
        "[I10_DRVS] transition hs=%s prev=%s new=%s intents=%s",
        health_subject_id,
        prev_status,
        new_effective.status,
        len(created),
    )
    return created
