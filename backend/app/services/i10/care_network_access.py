"""I10 HealthSubject caregiver access grant/write service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.care_network_actor import (
    CareNetworkAuthorizationError,
    require_actor_manage_subject_care_network,
)


class CareNetworkAccessError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _access_to_dict(row: models.AccountHealthSubjectAccess) -> dict:
    return {
        "id": row.id,
        "account_user_id": row.account_user_id,
        "health_subject_id": row.health_subject_id,
        "access_role": row.access_role,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "revoked_at": row.revoked_at,
    }


def grant_caregiver_subject_access(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
    recipient_account_user_id: int,
    access_role: str = "CAREGIVER",
    commit: bool = True,
) -> models.AccountHealthSubjectAccess:
    if access_role not in ("CAREGIVER", "MANAGER"):
        raise CareNetworkAccessError("INVALID_ACCESS_ROLE")
    require_actor_manage_subject_care_network(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None:
        raise CareNetworkAccessError("HEALTH_SUBJECT_NOT_FOUND")
    recipient = db.query(models.User).filter(models.User.id == recipient_account_user_id).first()
    if recipient is None:
        raise CareNetworkAccessError("RECIPIENT_ACCOUNT_NOT_FOUND")
    if subject.linked_user_id == recipient_account_user_id and access_role != "SELF":
        raise CareNetworkAccessError("CAREGIVER_SUBSTITUTION_BLOCKED")
    existing = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == recipient_account_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )
    if existing is not None:
        return existing
    row = models.AccountHealthSubjectAccess(
        account_user_id=recipient_account_user_id,
        health_subject_id=health_subject_id,
        access_role=access_role,
        is_active=True,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def list_subject_caregiver_access(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
) -> list[dict]:
    require_actor_manage_subject_care_network(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    rows = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
            models.AccountHealthSubjectAccess.access_role.in_(("CAREGIVER", "MANAGER")),
        )
        .order_by(models.AccountHealthSubjectAccess.id.asc())
        .all()
    )
    return [_access_to_dict(r) for r in rows]


def revoke_caregiver_subject_access(
    db: Session,
    *,
    actor_user_id: int,
    health_subject_id: int,
    recipient_account_user_id: int,
    commit: bool = True,
) -> Optional[models.AccountHealthSubjectAccess]:
    require_actor_manage_subject_care_network(
        db,
        actor_user_id=actor_user_id,
        health_subject_id=health_subject_id,
    )
    row = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == recipient_account_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )
    if row is None:
        return None
    if row.access_role == "SELF":
        raise CareNetworkAccessError("CANNOT_REVOKE_SELF_ACCESS")
    now = _utc_now()
    row.is_active = False
    row.revoked_at = now
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row
