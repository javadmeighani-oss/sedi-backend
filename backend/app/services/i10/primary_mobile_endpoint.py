"""I10 V1 primary Android mobile endpoint lifecycle.

User.id remains canonical identity. PushDevice rows are delivery endpoints only.
This module does not own auth, clinical policy, or notification family meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.models import PushDevice, User

ANDROID_PLATFORM = "android"

NO_ACTIVE_PRIMARY_ENDPOINT = "NO_ACTIVE_PRIMARY_ENDPOINT"
MULTIPLE_ACTIVE_PRIMARY_ENDPOINTS = "MULTIPLE_ACTIVE_PRIMARY_ENDPOINTS"
ALLOW_PRIMARY_ENDPOINT = "ALLOW_PRIMARY_ENDPOINT"


class PrimaryMobileEndpointError(Exception):
    """Domain error mapped by the register router. Not an HTTP type."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class UserNotFoundForEndpoint(PrimaryMobileEndpointError):
    def __init__(self) -> None:
        super().__init__(404, "USER_NOT_FOUND")


class CrossUserTokenError(PrimaryMobileEndpointError):
    def __init__(self) -> None:
        super().__init__(403, "fcm_token does not belong to authenticated user")


class TokenInstallConflictError(PrimaryMobileEndpointError):
    def __init__(self) -> None:
        super().__init__(409, "fcm_token is already registered to another installation")


@dataclass(frozen=True)
class PrimaryMobileResolution:
    outcome: str
    token: Optional[str] = None
    device: Optional[PushDevice] = None


def _active_android_rows(db: Session, user_id: int) -> list[PushDevice]:
    return (
        db.query(PushDevice)
        .filter(
            PushDevice.user_id == user_id,
            PushDevice.is_active.is_(True),
            PushDevice.platform == ANDROID_PLATFORM,
        )
        .order_by(PushDevice.id.asc())
        .all()
    )


def resolve_primary_android_endpoint(db: Session, user_id: int) -> PrimaryMobileResolution:
    """Fail-closed V1 primary resolution. Never picks newest among many."""
    rows = _active_android_rows(db, user_id)
    if len(rows) == 0:
        return PrimaryMobileResolution(outcome=NO_ACTIVE_PRIMARY_ENDPOINT)
    if len(rows) > 1:
        return PrimaryMobileResolution(outcome=MULTIPLE_ACTIVE_PRIMARY_ENDPOINTS)
    row = rows[0]
    token = (row.fcm_token or "").strip() or None
    if not token:
        return PrimaryMobileResolution(outcome=NO_ACTIVE_PRIMARY_ENDPOINT)
    return PrimaryMobileResolution(outcome=ALLOW_PRIMARY_ENDPOINT, token=token, device=row)


def _retire_superseded_android(
    db: Session,
    *,
    user_id: int,
    canonical: PushDevice,
    now: datetime,
) -> None:
    others = (
        db.query(PushDevice)
        .filter(
            PushDevice.user_id == user_id,
            PushDevice.platform == ANDROID_PLATFORM,
            PushDevice.is_active.is_(True),
            PushDevice.id != canonical.id,
        )
        .all()
    )
    for row in others:
        row.is_active = False
        row.updated_at = now
        db.add(row)


def reconcile_authenticated_registration(
    db: Session,
    *,
    auth_user_id: int,
    platform: str,
    fcm_token: str,
    device_id: Optional[str],
    now: datetime,
) -> tuple[PushDevice, bool]:
    """Lock the User row, upsert the canonical endpoint, retire other Android actives.

    Does not commit. Caller performs one commit after this returns.
    """
    user = (
        db.query(User)
        .filter(User.id == auth_user_id)
        .with_for_update()
        .first()
    )
    if user is None:
        raise UserNotFoundForEndpoint()

    token_row = db.query(PushDevice).filter(PushDevice.fcm_token == fcm_token).first()
    install_row = None
    if device_id:
        install_row = (
            db.query(PushDevice)
            .filter(
                PushDevice.user_id == auth_user_id,
                PushDevice.platform == platform,
                PushDevice.device_id == device_id,
            )
            .first()
        )

    if token_row is not None and token_row.user_id != auth_user_id:
        raise CrossUserTokenError()

    if device_id and install_row is not None:
        if token_row is not None and token_row.id != install_row.id:
            raise TokenInstallConflictError()
        canonical = install_row
        created = False
        canonical.fcm_token = fcm_token
        canonical.device_id = device_id
    elif token_row is not None:
        canonical = token_row
        created = False
        if device_id:
            canonical.device_id = device_id
    else:
        canonical = PushDevice(
            user_id=auth_user_id,
            platform=platform,
            fcm_token=fcm_token,
            device_id=device_id,
            is_active=True,
            last_seen_at=now,
            updated_at=now,
        )
        db.add(canonical)
        db.flush()
        created = True

    canonical.platform = platform
    canonical.is_active = True
    canonical.last_seen_at = now
    canonical.updated_at = now
    db.add(canonical)
    db.flush()
    _retire_superseded_android(
        db, user_id=auth_user_id, canonical=canonical, now=now
    )
    return canonical, created
