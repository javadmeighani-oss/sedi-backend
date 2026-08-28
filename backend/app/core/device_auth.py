# app/core/device_auth.py
"""
Device Authentication (Release C2)

Supports transition modes:
- legacy_only: shared token via DEVICE_INGEST_TOKEN
- db_only: per-device tokens stored in DB (devices table)
- hybrid (default): try DB first, fallback to legacy if enabled

Header name remains: X-DEVICE-TOKEN
"""

import os
import hashlib
import logging
from typing import Optional, Literal, Tuple
from datetime import datetime
import secrets

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.models import Device

logger = logging.getLogger(__name__)


DeviceAuthMode = Literal["hybrid", "db_only", "legacy_only"]


def _get_auth_mode() -> DeviceAuthMode:
    return os.getenv("DEVICE_AUTH_MODE", "hybrid").lower()  # type: ignore[return-value]


def _get_legacy_token() -> str:
    return os.getenv("DEVICE_INGEST_TOKEN", "")


def _hash_token(token: str) -> str:
    # Minimal, no external deps: sha256 hex digest
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_device_token() -> str:
    """
    Generate a random device token (shown only once to caller).
    token_urlsafe(32) produces ~43 chars (>=32 requirement).
    """
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    """Public helper for hashing device tokens (sha256 hex)."""
    return _hash_token(token)


def _token_snippet(token: str) -> str:
    """Safe prefix/suffix for logging (never full token)."""
    if not token or len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def get_device_token(x_device_token: str = Header(..., alias="X-DEVICE-TOKEN")) -> str:
    """
    Extract X-DEVICE-TOKEN header (always required on ingestion).
    """
    return (x_device_token or "").strip()


def validate_device_token(
    db: Session,
    user_id: int,
    device_id: str,
    token: str
) -> Optional[Device]:
    """
    Validate per-device token against DB (devices table).

    Rules:
    - device_id must exist, belong to user_id, status='active'
    - sha256(token) must match token_hash
    - update last_seen_at on success
    """
    token = (token or "").strip()
    token_hash = _hash_token(token)
    device = (
        db.query(Device)
        .filter(
            Device.device_id == device_id,
            Device.user_id == user_id
        )
        .first()
    )

    if not device:
        logger.debug(
            "[DEVICE_AUTH] validate_device_token reject reason=device_not_found device_id=%s user_id=%s token_snippet=%s",
            device_id, user_id, _token_snippet(token),
        )
        return None
    if device.status != "active":
        logger.debug(
            "[DEVICE_AUTH] validate_device_token reject reason=status_not_active device_id=%s status=%s token_snippet=%s",
            device_id, device.status, _token_snippet(token),
        )
        return None
    if device.token_hash != token_hash:
        logger.debug(
            "[DEVICE_AUTH] validate_device_token reject reason=token_hash_mismatch device_id=%s user_id=%s token_snippet=%s",
            device_id, user_id, _token_snippet(token),
        )
        return None

    # Update last_seen_at (best-effort)
    try:
        device.last_seen_at = datetime.utcnow()
        db.add(device)
        db.commit()
        db.refresh(device)
    except Exception:
        db.rollback()

    return device


def authorize_device_or_legacy(
    db: Session,
    user_id: int,
    device_id: Optional[str],
    token: str
) -> Tuple[str, Optional[Device]]:
    """
    Authorize ingestion using DEVICE_AUTH_MODE.

    Returns:
        (result, device)
        result in {"db", "legacy"}
    Raises:
        HTTPException on unauthorized / misconfigured
    """
    mode = _get_auth_mode()

    if mode not in ("hybrid", "db_only", "legacy_only"):
        mode = "hybrid"

    logger.debug(
        "[DEVICE_AUTH] authorize mode=%s device_id=%s user_id=%s token_snippet=%s",
        mode, device_id, user_id, _token_snippet(token),
    )

    # DB mode (requires device_id)
    if mode in ("hybrid", "db_only"):
        if not device_id:
            logger.info(f"[DEVICE_AUTH] mode={mode} result=missing_device_id user={user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="device_id is required for device auth"
            )
        # Validate token against the registered device row (not request user_id).
        # Ingest rejects user_id mismatch separately after auth succeeds.
        row = db.query(Device).filter(Device.device_id == device_id).first()
        device = None
        if row:
            device = validate_device_token(
                db=db,
                user_id=row.user_id,
                device_id=device_id,
                token=token,
            )
        if device:
            logger.info(
                "[DEVICE_AUTH] mode=%s result=db_ok device_id=%s device_user=%s request_user=%s",
                mode,
                device_id,
                device.user_id,
                user_id,
            )
            return "db", device
        logger.info(f"[DEVICE_AUTH] mode={mode} result=db_reject device_id={device_id} user={user_id}")
        if mode == "db_only":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")

    # Legacy fallback
    legacy = _get_legacy_token()
    if legacy and token == legacy.strip():
        logger.info(f"[DEVICE_AUTH] mode={mode} result=legacy_ok device_id={device_id} user={user_id}")
        return "legacy", None

    if mode == "legacy_only" and not legacy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device ingestion is not configured (DEVICE_INGEST_TOKEN not set)"
        )

    logger.debug(
        "[DEVICE_AUTH] reject reason=no_db_match_and_legacy_fail mode=%s device_id=%s user_id=%s token_snippet=%s",
        mode, device_id, user_id, _token_snippet(token),
    )
    logger.info(f"[DEVICE_AUTH] mode={mode} result=reject device_id={device_id} user={user_id}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")


def authorize_operational_device(
    db: Session,
    device_id: str,
    token: str,
) -> Device:
    """
    Authorize firmware-facing routes using registered per-device token only.

    Derives user identity from the validated device row (db_only semantics).
    """
    device_id = (device_id or "").strip()
    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id is required",
        )

    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        logger.info("[DEVICE_AUTH] operational reject reason=device_not_found device_id=%s", device_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")

    validated = validate_device_token(db=db, user_id=device.user_id, device_id=device_id, token=token)
    if not validated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")
    return validated


def resolve_device_from_token(db: Session, token: str) -> Optional[Device]:
    """Resolve active device row from bearer token hash (db_only operational path)."""
    token = (token or "").strip()
    if not token:
        return None
    token_hash = _hash_token(token)
    device = (
        db.query(Device)
        .filter(Device.token_hash == token_hash, Device.status == "active")
        .order_by(Device.id.desc())
        .first()
    )
    if device is None:
        return None
    device.last_seen_at = datetime.utcnow()
    db.add(device)
    db.flush()
    return device


def reject_legacy_user_id_query(request: Request) -> None:
    """Reject legacy user_id query param; identity comes from device token."""
    if request.query_params.get("user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "type": "extra_forbidden",
                    "loc": ["query", "user_id"],
                    "msg": "Extra inputs are not permitted",
                    "input": request.query_params.get("user_id"),
                }
            ],
        )


# Backward-compatible alias (Release C1)
def verify_device_token(x_device_token: str = Header(..., alias="X-DEVICE-TOKEN")) -> str:
    """
    Legacy verification helper. Kept for backward compatibility.
    Prefer using get_device_token + authorize_device_or_legacy.
    """
    legacy = _get_legacy_token()
    if not legacy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device ingestion is not configured (DEVICE_INGEST_TOKEN not set)"
        )
    if x_device_token != legacy:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")
    return x_device_token
