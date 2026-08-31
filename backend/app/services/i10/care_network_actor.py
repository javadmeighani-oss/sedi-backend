"""I10 care network actor authorization — subject-scoped management gates."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.health_subject_service import account_can_access_subject


class CareNetworkAuthorizationError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def get_active_subject_access(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
) -> models.AccountHealthSubjectAccess | None:
    return (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )


def actor_can_manage_subject_care_network(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
) -> bool:
    """MANAGER or SELF owner may manage caregiver access and notification grants.

    CAREGIVER role alone must not grant additional caregivers (fail-closed).
    """
    access = get_active_subject_access(
        db,
        account_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    if access is None:
        return False
    if access.access_role == "MANAGER":
        return True
    if access.access_role == "SELF":
        subject = (
            db.query(models.HealthSubject)
            .filter(models.HealthSubject.id == health_subject_id)
            .first()
        )
        return subject is not None and subject.linked_user_id == actor_user_id
    return False


def require_actor_manage_subject_care_network(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
) -> None:
    if not actor_can_manage_subject_care_network(db, actor_user_id=actor_user_id, health_subject_id=health_subject_id):
        raise CareNetworkAuthorizationError("ACTOR_CANNOT_MANAGE_SUBJECT_CARE_NETWORK")


def require_owner_caregiver(
    db: Session,
    *,
    owner_user_id: int,
    user_caregiver_id: int,
) -> models.UserCaregiver:
    row = (
        db.query(models.UserCaregiver)
        .filter(
            models.UserCaregiver.id == user_caregiver_id,
            models.UserCaregiver.owner_user_id == owner_user_id,
        )
        .first()
    )
    if row is None:
        raise CareNetworkAuthorizationError("USER_CAREGIVER_NOT_FOUND")
    return row
