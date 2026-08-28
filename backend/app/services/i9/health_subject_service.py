"""Health Subject foundation — account/subject separation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models


class HealthSubjectAccessDenied(Exception):
    pass


def ensure_self_subject_for_account(
    db: Session,
    account_user_id: int,
    *,
    display_name: Optional[str] = None,
    commit: bool = True,
) -> models.HealthSubject:
    """Create or return the SELF health subject for an account holder."""
    existing_access = (
        db.query(models.AccountHealthSubjectAccess)
        .join(models.HealthSubject)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.access_role == "SELF",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.HealthSubject.linked_user_id == account_user_id,
        )
        .first()
    )
    if existing_access is not None:
        return db.query(models.HealthSubject).filter(models.HealthSubject.id == existing_access.health_subject_id).one()

    user = db.query(models.User).filter(models.User.id == account_user_id).first()
    subject = models.HealthSubject(
        display_name=display_name or (user.name if user else None),
        linked_user_id=account_user_id,
        subject_kind="self",
        status="active",
    )
    db.add(subject)
    db.flush()
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=account_user_id,
            health_subject_id=subject.id,
            access_role="SELF",
            is_active=True,
        )
    )
    if commit:
        db.commit()
        db.refresh(subject)
    else:
        db.flush()
    return subject


def create_managed_subject_without_account(
    db: Session,
    *,
    account_user_id: int,
    display_name: str,
    access_role: str = "CAREGIVER",
    commit: bool = True,
) -> models.HealthSubject:
    """Managed health subject with no linked Sedi account."""
    if access_role not in ("CAREGIVER", "MANAGER"):
        raise ValueError("access_role must be CAREGIVER or MANAGER for managed subjects")
    subject = models.HealthSubject(
        display_name=display_name,
        linked_user_id=None,
        subject_kind="managed",
        status="active",
    )
    db.add(subject)
    db.flush()
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=account_user_id,
            health_subject_id=subject.id,
            access_role=access_role,
            is_active=True,
        )
    )
    if commit:
        db.commit()
        db.refresh(subject)
    else:
        db.flush()
    return subject


def account_can_access_subject(
    db: Session,
    account_user_id: int,
    health_subject_id: int,
) -> bool:
    row = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )
    return row is not None


def resolve_linked_user_id_for_subject(db: Session, health_subject_id: int) -> Optional[int]:
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    return subject.linked_user_id if subject else None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
