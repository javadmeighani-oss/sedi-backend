"""I10 subject-scoped notification grant management API service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.authorization import (
    I10AuthorizationError,
    create_notification_grant,
    get_active_notification_grant,
)
from backend.app.services.i10.care_network_actor import require_actor_manage_subject_care_network
from backend.app.services.i10.policy_types import I10NotificationScope, I10RecipientKind
from backend.app.services.i9.health_subject_service import account_can_access_subject


class CareNetworkGrantError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _grant_to_dict(row: models.HealthSubjectNotificationGrant) -> dict:
    return {
        "id": row.id,
        "health_subject_id": row.health_subject_id,
        "recipient_user_id": row.recipient_user_id,
        "notification_scope": row.notification_scope,
        "is_active": row.is_active,
        "authorization_source": row.authorization_source,
        "user_caregiver_id": row.user_caregiver_id,
        "granted_by_account_user_id": row.granted_by_account_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "revoked_at": row.revoked_at,
    }


def _require_recipient_access_before_grant(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
) -> None:
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None:
        raise CareNetworkGrantError("HEALTH_SUBJECT_NOT_FOUND")
    if subject.linked_user_id == recipient_user_id:
        return
    if not account_can_access_subject(db, recipient_user_id, health_subject_id):
        raise CareNetworkGrantError("RECIPIENT_LACKS_SUBJECT_ACCESS")


def create_subject_notification_grant(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    user_caregiver_id: Optional[int] = None,
    authorization_source: str = "MANUAL",
    commit: bool = True,
) -> models.HealthSubjectNotificationGrant:
    require_actor_manage_subject_care_network(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    recipient = db.query(models.User).filter(models.User.id == recipient_user_id).first()
    if recipient is None:
        raise CareNetworkGrantError("RECIPIENT_ACCOUNT_NOT_FOUND")
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None:
        raise CareNetworkGrantError("HEALTH_SUBJECT_NOT_FOUND")
    if subject.linked_user_id == recipient_user_id:
        raise CareNetworkGrantError("SELF_GRANT_NOT_REQUIRED")
    _require_recipient_access_before_grant(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
    )
    if user_caregiver_id is not None:
        caregiver = db.query(models.UserCaregiver).filter(models.UserCaregiver.id == user_caregiver_id).first()
        if caregiver is None or caregiver.owner_user_id != actor_user_id:
            raise CareNetworkGrantError("USER_CAREGIVER_NOT_FOUND")
    try:
        row = create_notification_grant(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_user_id,
            notification_scope=notification_scope,
            authorization_source=authorization_source,
            granted_by_account_user_id=actor_user_id,
            user_caregiver_id=user_caregiver_id,
            commit=commit,
        )
    except I10AuthorizationError as exc:
        raise CareNetworkGrantError(exc.code) from exc
    return row


def list_subject_notification_grants(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
    recipient_user_id: Optional[int] = None,
    active_only: bool = True,
) -> list[dict]:
    require_actor_manage_subject_care_network(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    q = db.query(models.HealthSubjectNotificationGrant).filter(
        models.HealthSubjectNotificationGrant.health_subject_id == health_subject_id,
    )
    if recipient_user_id is not None:
        q = q.filter(models.HealthSubjectNotificationGrant.recipient_user_id == recipient_user_id)
    if active_only:
        q = q.filter(
            models.HealthSubjectNotificationGrant.is_active.is_(True),
            models.HealthSubjectNotificationGrant.revoked_at.is_(None),
        )
    rows = q.order_by(models.HealthSubjectNotificationGrant.id.asc()).all()
    return [_grant_to_dict(r) for r in rows]


def revoke_subject_notification_grant(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
    grant_id: int,
    commit: bool = True,
) -> Optional[models.HealthSubjectNotificationGrant]:
    require_actor_manage_subject_care_network(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    row = (
        db.query(models.HealthSubjectNotificationGrant)
        .filter(
            models.HealthSubjectNotificationGrant.id == grant_id,
            models.HealthSubjectNotificationGrant.health_subject_id == health_subject_id,
        )
        .first()
    )
    if row is None:
        return None
    if not row.is_active or row.revoked_at is not None:
        return row
    now = _utc_now()
    row.is_active = False
    row.revoked_at = now
    row.updated_at = now
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def revoke_subject_notification_grant_by_scope(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
    recipient_user_id: int,
    notification_scope: I10NotificationScope,
    commit: bool = True,
) -> Optional[models.HealthSubjectNotificationGrant]:
    require_actor_manage_subject_care_network(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    row = get_active_notification_grant(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        notification_scope=notification_scope,
    )
    if row is None:
        return None
    return revoke_subject_notification_grant(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
        grant_id=row.id,
        commit=commit,
    )
