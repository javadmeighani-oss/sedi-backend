"""I10 recipient eligibility contract for future delivery (B06 foundation)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.authorization import get_active_notification_grant
from backend.app.services.i10.care_network_actor import get_active_subject_access
from backend.app.services.i10.policy_types import I10NotificationScope
from backend.app.services.i9.health_subject_service import account_can_access_subject


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

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_recipient_eligibility(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    user_caregiver_id: Optional[int] = None,
) -> CareNetworkRecipientEligibility:
    """Evaluate delivery eligibility without sending notifications or reading PushDevice."""
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


def _notification_pref_status(db: Session, user_id: int) -> str:
    prefs = db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == user_id).first()
    if prefs is None:
        return "DEFAULT"
    return "CONFIGURED"
