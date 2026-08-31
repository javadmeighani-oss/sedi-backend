"""I10 subject-scoped notification authorization — reusable care-network safety helpers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.policy_types import I10NotificationScope, I10RecipientKind
from backend.app.services.i9.health_subject_service import account_can_access_subject


class I10AuthorizationError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def phone_match_does_not_authorize() -> None:
    """Explicit guard: phone/contact match alone must never grant health notification auth."""
    raise I10AuthorizationError("PHONE_MATCH_NOT_AUTHORIZATION")


def resolve_recipient_kind(
    db: Session,
    *,
    recipient_user_id: int,
    health_subject_id: int,
) -> I10RecipientKind:
    subject = (
        db.query(models.HealthSubject)
        .filter(models.HealthSubject.id == health_subject_id)
        .first()
    )
    if subject is None:
        raise I10AuthorizationError("HEALTH_SUBJECT_NOT_FOUND")
    if subject.linked_user_id == recipient_user_id:
        return I10RecipientKind.SELF
    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == recipient_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )
    if access is None:
        raise I10AuthorizationError("RECIPIENT_LACKS_SUBJECT_ACCESS")
    if access.access_role == "MANAGER":
        return I10RecipientKind.MANAGER
    return I10RecipientKind.CAREGIVER


def get_active_notification_grant(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
) -> Optional[models.HealthSubjectNotificationGrant]:
    return (
        db.query(models.HealthSubjectNotificationGrant)
        .filter(
            models.HealthSubjectNotificationGrant.health_subject_id == health_subject_id,
            models.HealthSubjectNotificationGrant.recipient_user_id == recipient_user_id,
            models.HealthSubjectNotificationGrant.notification_scope == notification_scope.value,
            models.HealthSubjectNotificationGrant.is_active.is_(True),
            models.HealthSubjectNotificationGrant.revoked_at.is_(None),
        )
        .first()
    )


def create_notification_grant(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    authorization_source: str,
    granted_by_account_user_id: Optional[int] = None,
    user_caregiver_id: Optional[int] = None,
    commit: bool = True,
) -> models.HealthSubjectNotificationGrant:
    """Create an active subject-scoped notification grant.

    Linking ``user_caregiver_id`` records profile-relative provenance only.
    It does NOT authorize by itself.
    """
    if user_caregiver_id is not None:
        caregiver = db.query(models.UserCaregiver).filter(models.UserCaregiver.id == user_caregiver_id).first()
        if caregiver is None:
            raise I10AuthorizationError("USER_CAREGIVER_NOT_FOUND")
        # Profile link is metadata only — still require explicit grant creation path.
    existing = get_active_notification_grant(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope,
    )
    if existing is not None:
        return existing
    row = models.HealthSubjectNotificationGrant(
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope.value,
        is_active=True,
        authorization_source=authorization_source,
        user_caregiver_id=user_caregiver_id,
        granted_by_account_user_id=granted_by_account_user_id,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def validate_recipient_notification_authorization(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
) -> I10RecipientKind:
    """Fail-closed authorization for I10 delivery foundation.

    SELF recipients preserve legacy account behavior (no grant row required).
    Non-SELF recipients require AccountHealthSubjectAccess + active notification grant.
    """
    recipient_kind = resolve_recipient_kind(
        db,
        recipient_user_id=recipient_user_id,
        health_subject_id=health_subject_id,
    )
    if recipient_kind == I10RecipientKind.SELF:
        if not account_can_access_subject(db, recipient_user_id, health_subject_id):
            raise I10AuthorizationError("RECIPIENT_LACKS_SUBJECT_ACCESS")
        return recipient_kind
    if not account_can_access_subject(db, recipient_user_id, health_subject_id):
        raise I10AuthorizationError("RECIPIENT_LACKS_SUBJECT_ACCESS")
    grant = get_active_notification_grant(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope,
    )
    if grant is None:
        raise I10AuthorizationError("RECIPIENT_LACKS_NOTIFICATION_GRANT")
    return recipient_kind


def caregiver_profile_link_without_grant_is_insufficient(
    db: Session,
    *,
    user_caregiver_id: int,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
) -> None:
    """UserCaregiver linkage alone must not pass authorization."""
    caregiver = db.query(models.UserCaregiver).filter(models.UserCaregiver.id == user_caregiver_id).first()
    if caregiver is None:
        raise I10AuthorizationError("USER_CAREGIVER_NOT_FOUND")
    grant = get_active_notification_grant(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope,
    )
    if grant is None:
        raise I10AuthorizationError("PROFILE_LINK_WITHOUT_GRANT")
