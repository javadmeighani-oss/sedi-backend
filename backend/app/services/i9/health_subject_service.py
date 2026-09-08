"""Health Subject foundation — account/subject separation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import models


class HealthSubjectAccessDenied(Exception):
    pass


class HealthSubjectAmbiguousError(Exception):
    """Fail-closed when more than one effective ACTIVE SELF exists for an account."""


_SELF_UNIQUE_INDEX_MARKERS = (
    "uq_health_subjects_active_self_linked_user",
    "uq_ahsa_active_self_account",
)


def _is_expected_self_uniqueness_race(exc: BaseException) -> bool:
    msg = str(getattr(exc, "orig", None) or exc).lower()
    return any(marker in msg for marker in _SELF_UNIQUE_INDEX_MARKERS)


def resolve_canonical_active_self_subject(
    db: Session,
    account_user_id: int,
) -> Optional[models.HealthSubject]:
    """Return the single effective ACTIVE SELF for an account, or None.

    Fail-closed if more than one effective ACTIVE SELF row is present.
    """
    rows = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.linked_user_id == account_user_id,
            models.HealthSubject.subject_kind == "self",
            models.HealthSubject.status == "active",
        )
        .order_by(models.HealthSubject.id.asc())
        .all()
    )
    if len(rows) > 1:
        raise HealthSubjectAmbiguousError(
            f"Multiple active SELF HealthSubjects for account_user_id={account_user_id}"
        )
    if len(rows) == 1:
        return rows[0]
    return None


def _ensure_effective_self_ahsa(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
) -> None:
    """Ensure exactly one effective ACTIVE SELF AHSA points at the canonical subject."""
    active = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.access_role == "SELF",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .order_by(models.AccountHealthSubjectAccess.id.asc())
        .all()
    )
    if len(active) > 1:
        raise HealthSubjectAmbiguousError(
            f"Multiple effective SELF AHSA rows for account_user_id={account_user_id}"
        )
    if len(active) == 1:
        if int(active[0].health_subject_id) != int(health_subject_id):
            raise HealthSubjectAmbiguousError(
                "Effective SELF AHSA points at a different HealthSubject than canonical SELF"
            )
        return

    try:
        with db.begin_nested():
            db.add(
                models.AccountHealthSubjectAccess(
                    account_user_id=account_user_id,
                    health_subject_id=health_subject_id,
                    access_role="SELF",
                    is_active=True,
                )
            )
            db.flush()
    except IntegrityError as exc:
        if not _is_expected_self_uniqueness_race(exc):
            raise
        active2 = (
            db.query(models.AccountHealthSubjectAccess)
            .filter(
                models.AccountHealthSubjectAccess.account_user_id == account_user_id,
                models.AccountHealthSubjectAccess.access_role == "SELF",
                models.AccountHealthSubjectAccess.is_active.is_(True),
                models.AccountHealthSubjectAccess.revoked_at.is_(None),
            )
            .order_by(models.AccountHealthSubjectAccess.id.asc())
            .all()
        )
        if len(active2) != 1 or int(active2[0].health_subject_id) != int(health_subject_id):
            raise HealthSubjectAmbiguousError(
                f"SELF AHSA race recovery failed for account_user_id={account_user_id}"
            ) from exc


def ensure_self_subject_for_account(
    db: Session,
    account_user_id: int,
    *,
    display_name: Optional[str] = None,
    commit: bool = True,
) -> models.HealthSubject:
    """Create or return the canonical ACTIVE SELF health subject for an account holder.

    DB partial unique indexes are the final authority under concurrency.
    Expected uniqueness races recover via savepoint + re-resolve.
    Unexpected IntegrityError remains fail-closed.
    """
    existing = resolve_canonical_active_self_subject(db, account_user_id)
    if existing is not None:
        _ensure_effective_self_ahsa(
            db,
            account_user_id=account_user_id,
            health_subject_id=int(existing.id),
        )
        if commit:
            db.commit()
            db.refresh(existing)
        return existing

    user = db.query(models.User).filter(models.User.id == account_user_id).first()
    try:
        with db.begin_nested():
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
            db.flush()
    except IntegrityError as exc:
        if not _is_expected_self_uniqueness_race(exc):
            raise
        recovered = resolve_canonical_active_self_subject(db, account_user_id)
        if recovered is None:
            raise
        _ensure_effective_self_ahsa(
            db,
            account_user_id=account_user_id,
            health_subject_id=int(recovered.id),
        )
        if commit:
            db.commit()
            db.refresh(recovered)
        else:
            db.flush()
        return recovered

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


def require_account_subject_access(
    db: Session,
    account_user_id: int,
    health_subject_id: int,
) -> models.HealthSubject:
    """Fail-closed subject resolution for longitudinal reads."""
    if not account_can_access_subject(db, account_user_id, health_subject_id):
        raise HealthSubjectAccessDenied()
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None or subject.status != "active":
        raise HealthSubjectAccessDenied()
    return subject


def preferred_language_for_subject(db: Session, subject: models.HealthSubject) -> Optional[str]:
    if subject.linked_user_id is None:
        return None
    user = db.query(models.User).filter(models.User.id == subject.linked_user_id).first()
    return user.preferred_language if user else None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
