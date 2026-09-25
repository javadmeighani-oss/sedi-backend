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
DEFAULT_MEMORY_SOURCE = "product_default_v1"
DEFAULT_MEMORY_PROVENANCE = "service_default"
DEFAULT_MEMORY_POLICY_VERSION = "i6-v1"
_DEFAULT_MEMORY_PERMISSIONS = (PERM_WRITE, PERM_READ, PERM_FORGET)


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
    from backend.app.services.i7.derived_invalidation import invalidate_derived_memory_state

    invalidate_derived_memory_state(db, user_id, reason=reason, commit=commit)
    return True


def get_memory_consent_status(db: Session, user_id: int) -> dict:
    """Non-sensitive consent status for the authenticated user."""
    consent = _active_consent(db, user_id=user_id)
    return {
        "granted": consent is not None,
        "status": consent.status if consent is not None else "none",
        "permissions": {
            PERM_WRITE: has_permission(db, user_id, PERM_WRITE),
            PERM_READ: has_permission(db, user_id, PERM_READ),
            PERM_FORGET: has_permission(db, user_id, PERM_FORGET),
        },
        "policy_version": consent.policy_version if consent is not None else None,
    }


def _matching_memory_consents(db: Session, user_id: int) -> list[models.UserConsent]:
    return (
        db.query(models.UserConsent)
        .filter(
            models.UserConsent.subject_user_id == user_id,
            models.UserConsent.consent_type == MEMORY_CONSENT_TYPE,
            models.UserConsent.purpose == MEMORY_PURPOSE,
            models.UserConsent.grantee_type == GRANTEE_TYPE_SYSTEM,
            models.UserConsent.grantee_id == GRANTEE_ID_SEDI,
        )
        .all()
    )


def _ensure_scopes(
    db: Session,
    consent: models.UserConsent,
    permissions: tuple[str, ...] = _DEFAULT_MEMORY_PERMISSIONS,
) -> None:
    for key in permissions:
        scope = (
            db.query(models.UserConsentScope)
            .filter_by(consent_id=consent.id, permission_key=key)
            .first()
        )
        if scope is None:
            db.add(models.UserConsentScope(consent_id=consent.id, permission_key=key, allowed=True))
        elif scope.allowed is not True:
            scope.allowed = True


def ensure_default_memory_enabled(
    db: Session,
    user_id: int,
    *,
    commit: bool = True,
) -> Optional[models.UserConsent]:
    """Enable I6 memory as product default only when no prior decision exists.

    A) Active consent is preserved; missing default scopes are ensured.
    B) Any matching revoked/expired historical decision is never auto-enabled.
    C) Only when no matching historical row exists is a default record created.
    """
    now = _utcnow()
    rows = _matching_memory_consents(db, user_id)
    active: Optional[models.UserConsent] = None
    historical_block = False
    for row in rows:
        until = row.effective_until
        if until is not None and until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        status = row.status
        if status == "active" and until is not None and until <= now:
            row.status = "expired"
            row.updated_at = now
            status = "expired"
        if status == "active":
            active = row
        else:
            historical_block = True

    if active is not None:
        _ensure_scopes(db, active)
        if commit:
            db.commit()
            db.refresh(active)
        else:
            db.flush()
        return active

    if historical_block or rows:
        if commit:
            db.commit()
        else:
            db.flush()
        return None

    row = models.UserConsent(
        subject_user_id=user_id,
        consent_type=MEMORY_CONSENT_TYPE,
        purpose=MEMORY_PURPOSE,
        scope_summary="I6 personal long-term memory",
        grantee_type=GRANTEE_TYPE_SYSTEM,
        grantee_id=GRANTEE_ID_SEDI,
        status="active",
        policy_version=DEFAULT_MEMORY_POLICY_VERSION,
        granted_at=now,
        effective_from=now,
        source=DEFAULT_MEMORY_SOURCE,
        provenance=DEFAULT_MEMORY_PROVENANCE,
    )
    db.add(row)
    db.flush()
    _ensure_scopes(db, row)
    if commit:
        db.commit()
        db.refresh(row)
    return row


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
