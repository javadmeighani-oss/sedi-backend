"""C04 managed-person HealthSubject lifecycle (minimal V1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    create_managed_subject_without_account,
    require_account_subject_access,
)


class ManagedPersonError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def subject_public_dict(
    subject: models.HealthSubject,
    *,
    access_role: Optional[str] = None,
) -> dict:
    payload = {
        "health_subject_id": subject.id,
        "display_name": subject.display_name,
        "linked_user_id": subject.linked_user_id,
        "subject_kind": subject.subject_kind,
        "status": subject.status,
        "created_at": subject.created_at.isoformat() if subject.created_at else None,
        "updated_at": subject.updated_at.isoformat() if subject.updated_at else None,
    }
    if access_role is not None:
        payload["access_role"] = access_role
    return payload


def list_accessible_health_subjects(
    db: Session,
    *,
    account_user_id: int,
    include_inactive: bool = False,
) -> list[dict]:
    q = (
        db.query(models.HealthSubject, models.AccountHealthSubjectAccess)
        .join(
            models.AccountHealthSubjectAccess,
            models.AccountHealthSubjectAccess.health_subject_id == models.HealthSubject.id,
        )
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .order_by(models.HealthSubject.id.asc())
    )
    if not include_inactive:
        q = q.filter(models.HealthSubject.status == "active")
    rows = q.all()
    return [subject_public_dict(subject, access_role=access.access_role) for subject, access in rows]


def get_accessible_health_subject(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
) -> dict:
    subject = require_account_subject_access(db, account_user_id, health_subject_id)
    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )
    return subject_public_dict(subject, access_role=access.access_role if access else None)


def create_managed_person(
    db: Session,
    *,
    account_user_id: int,
    display_name: str,
    access_role: str = "MANAGER",
    idempotency_key: Optional[str] = None,
    commit: bool = True,
) -> tuple[models.HealthSubject, bool]:
    """Create managed accountless HealthSubject. Returns (subject, created_new)."""
    key = (idempotency_key or "").strip() or None
    if key is not None:
        existing = (
            db.query(models.HealthSubject)
            .filter(
                models.HealthSubject.created_by_account_user_id == account_user_id,
                models.HealthSubject.creation_idempotency_key == key,
            )
            .first()
        )
        if existing is not None:
            return existing, False

    subject = create_managed_subject_without_account(
        db,
        account_user_id=account_user_id,
        display_name=display_name.strip(),
        access_role=access_role,
        commit=False,
    )
    subject.created_by_account_user_id = account_user_id
    subject.creation_idempotency_key = key
    if commit:
        db.commit()
        db.refresh(subject)
    else:
        db.flush()
    return subject, True


def update_managed_person_profile(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
    display_name: Optional[str] = None,
    commit: bool = True,
) -> models.HealthSubject:
    subject = require_account_subject_access(db, account_user_id, health_subject_id)
    if subject.subject_kind != "managed":
        raise ManagedPersonError("NOT_MANAGED_SUBJECT")
    if subject.status != "active":
        raise ManagedPersonError("HEALTH_SUBJECT_INACTIVE")
    if display_name is not None:
        name = display_name.strip()
        if not name:
            raise ManagedPersonError("DISPLAY_NAME_REQUIRED")
        subject.display_name = name
        subject.updated_at = _utc_now()
    if commit:
        db.commit()
        db.refresh(subject)
    else:
        db.flush()
    return subject


def archive_managed_person(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
    commit: bool = True,
) -> models.HealthSubject:
    """Soft-deactivate managed subject. Preserves health/device/notification history."""
    subject = require_account_subject_access(db, account_user_id, health_subject_id)
    if subject.subject_kind != "managed":
        raise ManagedPersonError("NOT_MANAGED_SUBJECT")
    if subject.linked_user_id is not None:
        raise ManagedPersonError("ACCOUNTLESS_REQUIRED")
    if subject.status == "inactive":
        return subject

    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
            models.AccountHealthSubjectAccess.access_role.in_(("MANAGER", "CAREGIVER")),
        )
        .first()
    )
    if access is None:
        raise HealthSubjectAccessDenied()

    subject.status = "inactive"
    subject.updated_at = _utc_now()
    # Do not delete DeviceSubjectBinding, measurements, notifications, or conditions.
    if commit:
        db.commit()
        db.refresh(subject)
    else:
        db.flush()
    return subject
