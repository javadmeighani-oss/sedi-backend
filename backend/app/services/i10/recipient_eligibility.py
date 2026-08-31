"""I10 recipient resolution + delivery-time eligibility (B05/B06)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.authorization import get_active_notification_grant
from backend.app.services.i10.care_network_actor import get_active_subject_access
from backend.app.services.i10.delivery_readiness import has_active_push_device, notification_prefs_allow_scope
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.health_subject_service import account_can_access_subject

SCOPE_TO_SEMANTIC: dict[I10NotificationScope, I10SemanticFamily] = {
    I10NotificationScope.GENERAL_STATUS: I10SemanticFamily.GENERAL_STATUS,
    I10NotificationScope.DEVICE_STATUS: I10SemanticFamily.DEVICE_STATUS,
    I10NotificationScope.CARE_ACTION: I10SemanticFamily.CARE_ACTION,
    I10NotificationScope.SAFETY_ESCALATION: I10SemanticFamily.SAFETY_ESCALATION,
    I10NotificationScope.SENSITIVE_HEALTH_DETAIL: I10SemanticFamily.GENERAL_STATUS,
}


@dataclass
class CareNetworkRecipientEligibility:
    health_subject_id: int
    recipient_user_id: int
    user_caregiver_id: Optional[int] = None
    access_role: Optional[str] = None
    allowed_scopes: list[str] = field(default_factory=list)
    preferred_language: Optional[str] = None
    notification_pref_status: str = "UNKNOWN"
    eligible: bool = False
    reason_code: str = "NOT_EVALUATED"
    prefs_allowed: bool = True
    push_device_ready: bool = False
    delivery_ready: bool = False
    delivery_reason_code: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_recipient_eligibility(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    user_caregiver_id: Optional[int] = None,
    include_delivery_readiness: bool = False,
) -> CareNetworkRecipientEligibility:
    """Evaluate authorization eligibility; optional delivery readiness (prefs/PushDevice)."""
    result = _evaluate_authorization(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope,
        user_caregiver_id=user_caregiver_id,
    )
    if not include_delivery_readiness:
        return result
    return _apply_delivery_readiness(db, result, notification_scope)


def evaluate_delivery_eligibility(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    user_caregiver_id: Optional[int] = None,
) -> CareNetworkRecipientEligibility:
    """Delivery-time fail-closed evaluation including prefs and PushDevice readiness."""
    return evaluate_recipient_eligibility(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope,
        user_caregiver_id=user_caregiver_id,
        include_delivery_readiness=True,
    )


def resolve_care_network_recipients(
    db: Session,
    *,
    health_subject_id: int,
    notification_scope: I10NotificationScope,
    include_non_delivery_ready: bool = False,
) -> list[CareNetworkRecipientEligibility]:
    """Resolve Sedi-account caregivers for a subject — no phone-only recipients."""
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None or subject.status != "active":
        return []
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
    results: list[CareNetworkRecipientEligibility] = []
    seen: set[int] = set()
    for access in accesses:
        rid = access.account_user_id
        if rid in seen:
            continue
        seen.add(rid)
        if subject.linked_user_id == rid:
            continue
        ev = evaluate_delivery_eligibility(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=rid,
            notification_scope=notification_scope,
        )
        if not ev.eligible:
            if include_non_delivery_ready:
                results.append(ev)
            continue
        if ev.delivery_ready or include_non_delivery_ready:
            results.append(ev)
    return results


def _evaluate_authorization(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    user_caregiver_id: Optional[int],
) -> CareNetworkRecipientEligibility:
    result = CareNetworkRecipientEligibility(
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        user_caregiver_id=user_caregiver_id,
    )
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None or subject.status != "active":
        result.reason_code = "HEALTH_SUBJECT_NOT_FOUND"
        return result
    recipient = db.query(models.User).filter(models.User.id == recipient_user_id).first()
    if recipient is None:
        result.reason_code = "RECIPIENT_ACCOUNT_NOT_FOUND"
        return result
    result.preferred_language = recipient.preferred_language
    if user_caregiver_id is not None:
        caregiver = db.query(models.UserCaregiver).filter(models.UserCaregiver.id == user_caregiver_id).first()
        if caregiver is None:
            result.reason_code = "USER_CAREGIVER_NOT_FOUND"
            return result
        if not caregiver.is_active:
            result.reason_code = "USER_CAREGIVER_INACTIVE"
            return result
        if caregiver.linked_account_user_id is not None and caregiver.linked_account_user_id != recipient_user_id:
            result.reason_code = "USER_CAREGIVER_LINK_MISMATCH"
            return result
    access = get_active_subject_access(
        db,
        account_user_id=recipient_user_id,
        health_subject_id=health_subject_id,
    )
    if access is None:
        result.reason_code = "RECIPIENT_LACKS_SUBJECT_ACCESS"
        return result
    result.access_role = access.access_role
    if subject.linked_user_id == recipient_user_id:
        result.allowed_scopes = [s.value for s in I10NotificationScope]
        result.notification_pref_status = _notification_pref_status(db, recipient_user_id)
        result.eligible = True
        result.reason_code = "SELF_ELIGIBLE"
        return result
    grant = get_active_notification_grant(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope,
    )
    if grant is None:
        result.reason_code = "RECIPIENT_LACKS_NOTIFICATION_GRANT"
        return result
    active_scopes = [
        g.notification_scope
        for g in db.query(models.HealthSubjectNotificationGrant)
        .filter(
            models.HealthSubjectNotificationGrant.health_subject_id == health_subject_id,
            models.HealthSubjectNotificationGrant.recipient_user_id == recipient_user_id,
            models.HealthSubjectNotificationGrant.is_active.is_(True),
            models.HealthSubjectNotificationGrant.revoked_at.is_(None),
        )
        .all()
    ]
    result.allowed_scopes = active_scopes
    result.notification_pref_status = _notification_pref_status(db, recipient_user_id)
    if not account_can_access_subject(db, recipient_user_id, health_subject_id):
        result.reason_code = "RECIPIENT_LACKS_SUBJECT_ACCESS"
        return result
    result.eligible = True
    result.reason_code = "ELIGIBLE"
    return result


def _apply_delivery_readiness(
    db: Session,
    result: CareNetworkRecipientEligibility,
    notification_scope: I10NotificationScope,
) -> CareNetworkRecipientEligibility:
    if not result.eligible:
        result.delivery_ready = False
        result.delivery_reason_code = result.reason_code
        return result
    prefs_ok, prefs_reason = notification_prefs_allow_scope(db, result.recipient_user_id, notification_scope)
    result.prefs_allowed = prefs_ok
    result.push_device_ready = has_active_push_device(db, result.recipient_user_id)
    if not prefs_ok:
        result.delivery_ready = False
        result.delivery_reason_code = prefs_reason
        return result
    if not result.push_device_ready:
        result.delivery_ready = False
        result.delivery_reason_code = "NO_PUSH_DEVICE"
        return result
    result.delivery_ready = True
    result.delivery_reason_code = "DELIVERY_READY"
    return result


def _notification_pref_status(db: Session, user_id: int) -> str:
    prefs = db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == user_id).first()
    if prefs is None:
        return "DEFAULT"
    return "CONFIGURED"
