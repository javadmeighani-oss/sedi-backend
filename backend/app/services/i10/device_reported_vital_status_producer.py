"""I10 DEVICE_STATUS — gadget-reported vital status transitions to caregivers.

Authority: I9 DeviceReportedVitalStatus only. No MAD/RAG/LLM/clinical inference.
"""

from __future__ import annotations

import logging
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
    if previous_status is None and new_status == STATUS_STABLE:
        return "Gadget reports Mother's vital-sign status as stable."
    if previous_status is None and new_status == STATUS_UNSTABLE:
        return "Gadget reports Mother's vital-sign status as unstable/changed. Please check on her."
    if previous_status == STATUS_STABLE and new_status == STATUS_UNSTABLE:
        return "Gadget reports Mother's vital-sign status as unstable/changed. Please check on her."
    if previous_status == STATUS_UNSTABLE and new_status == STATUS_STABLE:
        return "Gadget reports Mother's status has returned to stable."
    # Should not notify on same→same; fail-closed generic device wording.
    return f"Gadget reports Mother's vital-sign status as {new_status.lower()}."


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
        # Out-of-order / non-effective historical row — do not corrupt/notify.
        return False
    prev_status = previous.status if previous is not None else None
    if prev_status == new_effective.status:
        return False
    return True


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
