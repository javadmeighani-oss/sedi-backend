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

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app.models import Device

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


def get_device_token(x_device_token: str = Header(..., alias="X-DEVICE-TOKEN")) -> str:
    """
    Extract X-DEVICE-TOKEN header (always required on ingestion).
    """
    return x_device_token


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
        return None
    if device.status != "active":
        return None
    if device.token_hash != token_hash:
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

    # DB mode (requires device_id)
    if mode in ("hybrid", "db_only"):
        if not device_id:
            logger.info(f"[DEVICE_AUTH] mode={mode} result=missing_device_id user={user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="device_id is required for device auth"
            )
        device = validate_device_token(db=db, user_id=user_id, device_id=device_id, token=token)
        if device:
            logger.info(f"[DEVICE_AUTH] mode={mode} result=db_ok device_id={device_id} user={user_id}")
            return "db", device
        logger.info(f"[DEVICE_AUTH] mode={mode} result=db_reject device_id={device_id} user={user_id}")
        if mode == "db_only":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")

    # Legacy fallback
    legacy = _get_legacy_token()
    if legacy and token == legacy:
        logger.info(f"[DEVICE_AUTH] mode={mode} result=legacy_ok device_id={device_id} user={user_id}")
        return "legacy", None

    if mode == "legacy_only" and not legacy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device ingestion is not configured (DEVICE_INGEST_TOKEN not set)"
        )

    logger.info(f"[DEVICE_AUTH] mode={mode} result=reject device_id={device_id} user={user_id}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")


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
