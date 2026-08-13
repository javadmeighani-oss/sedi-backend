"""I6 consent grant/revoke/expire/scope checks on existing user_consents tables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models

MEMORY_CONSENT_TYPE = "MEMORY"
MEMORY_PURPOSE = "PERSONAL_LONG_TERM_MEMORY"
GRANTEE_TYPE_SYSTEM = "SYSTEM"
GRANTEE_ID_SEDI = "sedi"
PERM_WRITE = "memory.write"
PERM_READ = "memory.read"
PERM_FORGET = "memory.forget"


class ConsentDenied(PermissionError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _active_consent(
    db: Session,
    *,
    user_id: int,
    consent_type: str = MEMORY_CONSENT_TYPE,
    purpose: str = MEMORY_PURPOSE,
) -> Optional[models.UserConsent]:
    now = _utcnow()
    rows = (
        db.query(models.UserConsent)
        .filter(
            models.UserConsent.subject_user_id == user_id,
            models.UserConsent.consent_type == consent_type,
            models.UserConsent.purpose == purpose,
            models.UserConsent.status == "active",
        )
        .all()
    )
    for row in rows:
        until = row.effective_until
        if until is not None and until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until is not None and until <= now:
            row.status = "expired"
            row.updated_at = now
            continue
        return row
    return None


def has_permission(db: Session, user_id: int, permission_key: str) -> bool:
    consent = _active_consent(db, user_id=user_id)
    if consent is None:
        return False
    scope = (
        db.query(models.UserConsentScope)
        .filter(
            models.UserConsentScope.consent_id == consent.id,
            models.UserConsentScope.permission_key == permission_key,
            models.UserConsentScope.allowed.is_(True),
        )
        .first()
    )
    return scope is not None


def require_permission(db: Session, user_id: int, permission_key: str) -> models.UserConsent:
    if not has_permission(db, user_id, permission_key):
        raise ConsentDenied(f"CONSENT_DENIED:{permission_key}")
    consent = _active_consent(db, user_id=user_id)
    if consent is None:
        raise ConsentDenied(f"CONSENT_DENIED:{permission_key}")
    return consent


def grant_memory_consent(
    db: Session,
    user_id: int,
    *,
    permissions: tuple[str, ...] = (PERM_WRITE, PERM_READ, PERM_FORGET),
    policy_version: str = "i6-v1",
    commit: bool = True,
) -> models.UserConsent:
    now = _utcnow()
    existing = _active_consent(db, user_id=user_id)
    if existing is not None:
        for key in permissions:
            scope = (
                db.query(models.UserConsentScope)
                .filter_by(consent_id=existing.id, permission_key=key)
                .first()
            )
            if scope is None:
                db.add(models.UserConsentScope(consent_id=existing.id, permission_key=key, allowed=True))
            else:
                scope.allowed = True
        if commit:
            db.commit()
            db.refresh(existing)
        return existing
    row = models.UserConsent(
        subject_user_id=user_id,
        consent_type=MEMORY_CONSENT_TYPE,
        purpose=MEMORY_PURPOSE,
        scope_summary="I6 personal long-term memory",
        grantee_type=GRANTEE_TYPE_SYSTEM,
        grantee_id=GRANTEE_ID_SEDI,
        status="active",
        policy_version=policy_version,
        granted_at=now,
        effective_from=now,
        source="i6_consent_service",
        provenance="user_granted",
    )
    db.add(row)
    db.flush()
    for key in permissions:
        db.add(models.UserConsentScope(consent_id=row.id, permission_key=key, allowed=True))
    if commit:
        db.commit()
        db.refresh(row)
    return row


def revoke_memory_consent(
    db: Session, user_id: int, *, reason: str = "user_revoked", commit: bool = True
) -> bool:
    consent = _active_consent(db, user_id=user_id)
    if consent is None:
        return False
    now = _utcnow()
    consent.status = "revoked"
    consent.revoked_at = now
    consent.revocation_reason = reason
    consent.updated_at = now
    if commit:
        db.commit()
    else:
        db.flush()
    return True


def expire_due_consents(
    db: Session, user_id: Optional[int] = None, *, commit: bool = True
) -> int:
    now = _utcnow()
    q = db.query(models.UserConsent).filter(models.UserConsent.status == "active")
    if user_id is not None:
        q = q.filter(models.UserConsent.subject_user_id == user_id)
    count = 0
    for row in q.all():
        until = row.effective_until
        if until is None:
            continue
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until <= now:
            row.status = "expired"
            row.updated_at = now
            count += 1
    if count:
        if commit:
            db.commit()
        else:
            db.flush()
    return count
