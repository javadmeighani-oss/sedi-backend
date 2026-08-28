"""Device claim lifecycle — platform identity separate from subject binding."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.core.device_token_crypto import generate_device_token, hash_device_token
from backend.app.services.i9.device_binding_service import bind_device_to_subject, get_active_binding
from backend.app.services.i9.device_credential_verifier import (
    credential_fingerprint_from_hash,
    get_device_credential_verifier,
)
from backend.app.services.i9.device_lifecycle_service import record_lifecycle_audit
from backend.app.services.i9.health_subject_service import account_can_access_subject


class DeviceClaimError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def provision_unclaimed_device_platform(
    db: Session,
    *,
    device_id: str,
    device_type: str = "heart_rate",
    commit: bool = True,
) -> Tuple[models.Device, str]:
    """Create platform identity eligible for governed initial claim."""
    existing = db.query(models.Device).filter(models.Device.device_id == device_id).first()
    if existing is not None:
        raise DeviceClaimError("DEVICE_ID_TAKEN", "device_id already exists")

    token = generate_device_token()
    token_hash = hash_device_token(token)
    device = models.Device(
        user_id=None,
        owner_account_user_id=None,
        device_id=device_id,
        device_type=device_type,
        status="active",
        claim_lifecycle_status="unclaimed",
        credential_kind="per_device_symmetric",
        credential_fingerprint=credential_fingerprint_from_hash(token_hash),
        token_hash=token_hash,
        created_at=utc_now(),
    )
    db.add(device)
    db.flush()
    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="provision_unclaimed",
        actor_account_user_id=None,
        detail={"device_id": device_id},
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(device)
    return device, token


def assert_device_claim_eligible(db: Session, device: models.Device) -> None:
    if device.claim_lifecycle_status == "claimed":
        active = get_active_binding(db, device.id)
        if active is not None:
            raise DeviceClaimError("CLAIMED_DEVICE_RECLAIM_FORBIDDEN", "Device is already claimed and bound")
        raise DeviceClaimError("DEVICE_ALREADY_CLAIMED", "Device is already claimed")
    if device.claim_lifecycle_status == "revoked":
        raise DeviceClaimError("DEVICE_REVOKED", "Device is revoked")
    if device.claim_lifecycle_status == "suspended":
        raise DeviceClaimError("DEVICE_SUSPENDED", "Device is suspended")
    if device.claim_lifecycle_status not in ("unclaimed", "released"):
        raise DeviceClaimError(
            "DEVICE_NOT_CLAIMABLE",
            f"Device claim status '{device.claim_lifecycle_status}' is not claimable",
        )


def claim_device_to_health_subject(
    db: Session,
    *,
    device: models.Device,
    account_user_id: int,
    health_subject_id: int,
    possession_proof: str,
    gateway_install_id: Optional[str] = None,
    commit: bool = True,
) -> models.DeviceSubjectBinding:
    """Governed claim: verify possession proof, authorize subject, create binding."""
    if device.claim_lifecycle_status == "claimed":
        active = get_active_binding(db, device.id)
        if active is not None:
            raise DeviceClaimError("CLAIMED_DEVICE_RECLAIM_FORBIDDEN", "Already claimed device cannot be silently re-claimed")
        raise DeviceClaimError("DEVICE_ALREADY_CLAIMED", "Device is already claimed")

    if device.claim_lifecycle_status not in ("unclaimed", "released"):
        raise DeviceClaimError("DEVICE_NOT_CLAIMABLE", f"Device status '{device.claim_lifecycle_status}' blocks claim")

    if not account_can_access_subject(db, account_user_id, health_subject_id):
        raise DeviceClaimError("HEALTH_SUBJECT_ACCESS_DENIED", "Account cannot manage this health subject")

    verifier = get_device_credential_verifier()
    verification = verifier.verify(device, possession_proof)
    if not verification.verified:
        code = verification.reject_reason or "POSSESSION_PROOF_FAILED"
        raise DeviceClaimError(code, "Device possession proof failed")

    binding = bind_device_to_subject(
        db,
        device=device,
        health_subject_id=health_subject_id,
        bound_by_account_user_id=account_user_id,
        commit=False,
    )
    device.claim_lifecycle_status = "claimed"
    device.owner_account_user_id = account_user_id
    device.user_id = account_user_id
    device.status = "active"
    device.revoked_at = None

    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="claim",
        actor_account_user_id=account_user_id,
        health_subject_id=health_subject_id,
        gateway_install_id=gateway_install_id,
        detail={"binding_id": binding.id},
        commit=False,
    )

    if gateway_install_id:
        from backend.app.services.i9.device_gateway_service import authorize_mobile_gateway

        authorize_mobile_gateway(
            db,
            device=device,
            gateway_install_id=gateway_install_id,
            account_user_id=account_user_id,
            commit=False,
        )

    if commit:
        db.commit()
        db.refresh(binding)
    else:
        db.flush()
    return binding
