"""I10 DEVICE_STATUS — gadget-reported vital status to SELF + authorized caregivers.

DRVS rows remain persisted. I10 minting is suppressed when canonical MAD HR
stability intents already exist for the same subject/day (anti-dupe).

SELF uses canonical I10 intake (NotificationBuilder) — never caregiver fiction.
Caregivers use DEVICE_STATUS grant + delivery-time revalidation path.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.i10.care_digest_producer_worker import (
    _authorized_recipients,
    resolve_subject_owner_user_id,
)
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
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
    audience: str = "caregiver",
) -> str:
    """Factual DEVICE_REPORTED wording. audience=self|caregiver."""
    if audience == "self":
        if previous_status is None and new_status == STATUS_STABLE:
            return "Gadget reports your vital-sign status as stable."
        if previous_status is None and new_status == STATUS_UNSTABLE:
            return "Gadget reports your vital-sign status as unstable/changed."
        if previous_status == STATUS_STABLE and new_status == STATUS_UNSTABLE:
            return "Gadget reports your vital-sign status as unstable/changed."
        if previous_status == STATUS_UNSTABLE and new_status == STATUS_STABLE:
            return "Gadget reports your vital-sign status has returned to stable."
        return f"Gadget reports your vital-sign status as {new_status.lower()}."

    # Caregiver / manager — generic subject wording; never hard-code a person label.
    if previous_status is None and new_status == STATUS_STABLE:
        return "Gadget reports the subject's vital-sign status as stable."
    if previous_status is None and new_status == STATUS_UNSTABLE:
        return "Gadget reports the subject's vital-sign status as unstable/changed. Please check on them."
    if previous_status == STATUS_STABLE and new_status == STATUS_UNSTABLE:
        return "Gadget reports the subject's vital-sign status as unstable/changed. Please check on them."
    if previous_status == STATUS_UNSTABLE and new_status == STATUS_STABLE:
        return "Gadget reports the subject's status has returned to stable."
    return f"Gadget reports the subject's vital-sign status as {new_status.lower()}."


def render_device_reported_vital_daily_body(*, status: str, audience: str = "self") -> str:
    if audience == "self":
        if status == STATUS_STABLE:
            return "Gadget reports your vital-sign status as stable."
        return "Gadget reports your vital-sign status as unstable/changed."
    if status == STATUS_STABLE:
        return "Gadget reports the subject's vital-sign status as stable."
    return "Gadget reports the subject's vital-sign status as unstable/changed. Please check on them."


def build_device_reported_vital_occurrence_key(
    *,
    health_subject_id: int,
    previous_status: Optional[str],
    new_status: str,
    status_row_id: int,
) -> str:
    prev = previous_status or "NONE"
    return f"i10:drv:{health_subject_id}:transition:{prev}:{new_status}:{status_row_id}"


def build_device_reported_vital_daily_occurrence_key(
    *,
    health_subject_id: int,
    period_date: date,
    status_row_id: int,
) -> str:
    return f"i10:drv:daily:{int(health_subject_id)}:{period_date.isoformat()}:{int(status_row_id)}"


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


def _period_date(when: datetime) -> date:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).date()


def _assert_safe_copy(body: str) -> None:
    lower = body.lower()
    # Do not match bare "safe" inside "stable".
    for forbidden in ("danger", "emergency", "diagnosis", "critical", "healthy", "medically"):
        if forbidden in lower:
            raise ValueError(f"FORBIDDEN_NOTIFICATION_LANGUAGE:{forbidden}")
    if "medically safe" in lower or " medically safe" in lower:
        raise ValueError("FORBIDDEN_NOTIFICATION_LANGUAGE:medically safe")


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


def _drv_daily_already_for_day(db: Session, *, health_subject_id: int, day_iso: str) -> bool:
    """ONE daily DRVS notification per subject/day (any effective_row_id)."""
    prefix = f"i10:drv:daily:{int(health_subject_id)}:{day_iso}:"
    cg = (
        db.query(models.CaregiverNotificationIntent.occurrence_key)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == int(health_subject_id),
            models.CaregiverNotificationIntent.occurrence_key.like(f"{prefix}%"),
        )
        .first()
    )
    if cg is not None:
        return True
    decision = (
        db.query(models.I10NotificationDecision.candidate_key)
        .filter(models.I10NotificationDecision.candidate_key.like(f"{prefix}%"))
        .first()
    )
    return decision is not None


def _emit_self_via_intake(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    occurrence_key: str,
    title: str,
    body: str,
    status: str,
    previous_status: Optional[str],
    source_entity_id: int,
    trigger_reason: str,
) -> Optional[models.Notification]:
    _assert_safe_copy(body)
    payload = NotificationPayload(
        user_id=int(recipient_user_id),
        type="health_alert",
        title=title,
        body=body,
        priority="normal",
        dedupe_key=occurrence_key,
        metadata={
            "status": status,
            "previous_status": previous_status,
            "source_class": "DEVICE_REPORTED",
            "trigger_reason": trigger_reason,
        },
        category="health",
        source_type=PRODUCER_OWNER,
        source_id=str(int(source_entity_id)),
        context={
            "template_key": "device_reported_vital_status",
            "status": status,
            "previous_status": previous_status,
            "source_class": "DEVICE_REPORTED",
            "device_reported_vital_status_id": int(source_entity_id),
        },
        risk_level="low",
        template_key="device_reported_vital_status",
        health_subject_id=int(health_subject_id),
        semantic_family=I10SemanticFamily.DEVICE_STATUS.value,
        recipient_kind="SELF",
        privacy_class=I10PrivacyClass.HEALTH_SENSITIVE.value,
    )
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=int(health_subject_id),
        recipient_user_id=int(recipient_user_id),
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        source_owner=PRODUCER_OWNER,
        source_type="device_reported_vital_status",
        source_id=str(int(source_entity_id)),
        semantic_family=I10SemanticFamily.DEVICE_STATUS,
        privacy_hint=I10PrivacyClass.HEALTH_SENSITIVE,
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10_DRVS] self_intake suppressed hs=%s key=%s decision=%s reason=%s",
            health_subject_id,
            occurrence_key,
            result.decision,
            result.reason_code,
        )
        return None
    return db.query(models.Notification).filter(models.Notification.id == result.notification_id).first()


def emit_device_reported_vital_daily(
    db: Session,
    *,
    health_subject_id: int,
    effective: EffectiveVitalStatus,
    deliver: bool = False,
    commit: bool = True,
) -> list[models.CaregiverNotificationIntent]:
    """ONE governed daily gadget-health status notification per subject/day."""
    day = _period_date(effective.detected_at)
    day_iso = day.isoformat()
    if _drv_daily_already_for_day(db, health_subject_id=health_subject_id, day_iso=day_iso):
        return []
    if _canonical_hr_i10_already_emitted(
        db, health_subject_id=health_subject_id, when=effective.detected_at
    ):
        logger.info(
            "[I10_DRVS] daily suppressed hs=%s reason=canonical_hr_stability_already_emitted",
            health_subject_id,
        )
        return []

    occurrence = build_device_reported_vital_daily_occurrence_key(
        health_subject_id=health_subject_id,
        period_date=day,
        status_row_id=int(effective.row_id),
    )
    owner_id = resolve_subject_owner_user_id(db, health_subject_id)
    created: list[models.CaregiverNotificationIntent] = []

    if owner_id is not None:
        body = render_device_reported_vital_daily_body(status=effective.status, audience="self")
        _emit_self_via_intake(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=owner_id,
            occurrence_key=occurrence,
            title="Gadget health status",
            body=body,
            status=effective.status,
            previous_status=None,
            source_entity_id=int(effective.row_id),
            trigger_reason="device_reported_vital_status_daily",
        )

    caregiver_body = render_device_reported_vital_daily_body(
        status=effective.status, audience="caregiver"
    )
    _assert_safe_copy(caregiver_body)
    metadata = {
        "title": "Gadget health status",
        "body": caregiver_body,
        "template_key": "device_reported_vital_status_daily",
        "trigger_reason": "device_reported_vital_status_daily",
        "status": effective.status,
        "source_class": "DEVICE_REPORTED",
        "context": {
            "template_key": "device_reported_vital_status_daily",
            "status": effective.status,
            "source_class": "DEVICE_REPORTED",
            "device_reported_vital_status_id": int(effective.row_id),
        },
        "semantic_family": I10SemanticFamily.DEVICE_STATUS.value,
        "privacy_class": I10PrivacyClass.HEALTH_SENSITIVE.value,
        "source_entity_type": PRODUCER_OWNER,
        "source_entity_id": int(effective.row_id),
    }
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
            source_entity_id=int(effective.row_id),
            payload_metadata=metadata,
            commit=commit,
        )
        created.append(intent)
        if deliver and intent.status == "pending":
            process_caregiver_delivery_intent(db, intent, commit=commit)
    logger.info(
        "[I10_DRVS] daily hs=%s status=%s caregivers=%s",
        health_subject_id,
        effective.status,
        len(created),
    )
    return created


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
    created: list[models.CaregiverNotificationIntent] = []

    if new_effective is not None:
        created.extend(
            emit_device_reported_vital_daily(
                db,
                health_subject_id=health_subject_id,
                effective=new_effective,
                deliver=deliver,
                commit=commit,
            )
        )

    if not should_notify_device_reported_transition(
        previous=previous,
        new_effective=new_effective,
        ingested_row_id=int(ingested_row.id),
    ):
        return created

    assert new_effective is not None
    detected = ingested_row.detected_at
    if _canonical_hr_i10_already_emitted(db, health_subject_id=health_subject_id, when=detected):
        logger.info(
            "[I10_DRVS] transition suppressed_dupe hs=%s row=%s reason=canonical_hr_stability_already_emitted",
            health_subject_id,
            ingested_row.id,
        )
        return created

    prev_status = previous.status if previous is not None else None
    occurrence = build_device_reported_vital_occurrence_key(
        health_subject_id=health_subject_id,
        previous_status=prev_status,
        new_status=new_effective.status,
        status_row_id=int(ingested_row.id),
    )
    owner_id = resolve_subject_owner_user_id(db, health_subject_id)

    if owner_id is not None:
        self_body = render_device_reported_vital_status_body(
            previous_status=prev_status,
            new_status=new_effective.status,
            audience="self",
        )
        _emit_self_via_intake(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=owner_id,
            occurrence_key=f"{occurrence}:self",
            title="Device-reported vital status",
            body=self_body,
            status=new_effective.status,
            previous_status=prev_status,
            source_entity_id=int(ingested_row.id),
            trigger_reason="device_reported_vital_status_transition",
        )

    body = render_device_reported_vital_status_body(
        previous_status=prev_status,
        new_status=new_effective.status,
        audience="caregiver",
    )
    _assert_safe_copy(body)

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
