"""Device claim lifecycle — platform identity separate from subject binding."""

from __future__ import annotations

import re
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
from backend.app.services.i9.device_setup_code_service import (
    DeviceSetupCodeError,
    assert_setup_code_not_locked,
    assign_unique_setup_code,
    record_setup_code_failure,
    reset_setup_code_failure_state,
    utc_now,
    validate_category_and_label,
    verify_setup_code_constant_time,
)
from backend.app.services.i9.health_subject_service import account_can_access_subject

_V1_DEVICE_ID_RE = re.compile(r"^SEDI-[A-Z0-9]{2,12}-\d{12}$")


class DeviceClaimError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_v1_trusted_device_id(device_id: str) -> bool:
    return bool(_V1_DEVICE_ID_RE.match(device_id or ""))


def assert_v1_trusted_device_id(device_id: str) -> None:
    if not is_v1_trusted_device_id(device_id):
        raise DeviceClaimError(
            "DEVICE_ID_V1_FORMAT_REQUIRED",
            "device_id must match SEDI-<TYPE>-<12_DIGIT_SERIAL>",
        )


def provision_unclaimed_device_platform(
    db: Session,
    *,
    device_id: str,
    device_type: str = "heart_rate",
    commit: bool = True,
) -> Tuple[models.Device, str]:
    """Create platform identity eligible for governed initial claim.

    Canonical return contract: (device, plaintext_token).
    """
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
        created_at=utc_now().replace(tzinfo=None),
        setup_code_failed_attempts=0,
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


def provision_unclaimed_device_v1(
    db: Session,
    *,
    device_id: str,
    device_type: str = "heart_rate",
    commit: bool = True,
) -> Tuple[models.Device, str, str]:
    """Trusted V1 provision: reuse platform identity + attach setup-code authority once.

    Returns (device, plaintext_token, plaintext_setup_code).
    Does not create a parallel Device registry or claim lifecycle.
    """
    device, token = provision_unclaimed_device_platform(
        db,
        device_id=device_id,
        device_type=device_type,
        commit=False,
    )
    try:
        setup_code = assign_unique_setup_code(db, device, commit=False)
    except DeviceSetupCodeError as exc:
        raise DeviceClaimError(exc.code, exc.message) from exc
    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="provision_setup_code_attached",
        actor_account_user_id=None,
        detail={"setup_code_attached": True, "setup_code_version": device.setup_code_version},
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(device)
    return device, token, setup_code


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
    setup_code: Optional[str] = None,
    device_category: Optional[str] = None,
    user_label: Optional[str] = None,
    commit: bool = True,
) -> models.DeviceSubjectBinding:
    """Governed claim: verify possession proof, authorize subject, create binding.

    Canonical order for setup-code devices:
    claim eligible → lock → setup code → possession → subject access →
    category/label → binding → ownership → gateway → reset failures → COMMIT.
    """
    # Claim lifecycle eligibility
    if device.claim_lifecycle_status == "claimed":
        active = get_active_binding(db, device.id)
        if active is not None:
            raise DeviceClaimError(
                "CLAIMED_DEVICE_RECLAIM_FORBIDDEN",
                "Already claimed device cannot be silently re-claimed",
            )
        raise DeviceClaimError("DEVICE_ALREADY_CLAIMED", "Device is already claimed")

    if device.claim_lifecycle_status not in ("unclaimed", "released"):
        raise DeviceClaimError(
            "DEVICE_NOT_CLAIMABLE",
            f"Device status '{device.claim_lifecycle_status}' blocks claim",
        )

    requires_setup = bool(device.setup_code_verifier)
    if requires_setup:
        try:
            assert_setup_code_not_locked(device)
        except DeviceSetupCodeError as exc:
            raise DeviceClaimError(exc.code, exc.message) from exc
        if setup_code is None or not str(setup_code).strip():
            raise DeviceClaimError("SETUP_CODE_REQUIRED", "Setup code is required for this device")
        try:
            ok = verify_setup_code_constant_time(device, setup_code)
        except DeviceSetupCodeError as exc:
            record_setup_code_failure(db, device, commit=True)
            raise DeviceClaimError(exc.code, exc.message) from exc
        if not ok:
            record_setup_code_failure(db, device, commit=True)
            raise DeviceClaimError("SETUP_CODE_INVALID", "Setup code verification failed")

    verifier = get_device_credential_verifier()
    verification = verifier.verify(device, possession_proof)
    if not verification.verified:
        code = verification.reject_reason or "POSSESSION_PROOF_FAILED"
        raise DeviceClaimError(code, "Device possession proof failed")

    if not account_can_access_subject(db, account_user_id, health_subject_id):
        raise DeviceClaimError("HEALTH_SUBJECT_ACCESS_DENIED", "Account cannot manage this health subject")

    category: Optional[str] = None
    label: Optional[str] = None
    if requires_setup:
        try:
            category, label = validate_category_and_label(
                device_category=device_category,
                user_label=user_label,
                require_category=True,
            )
        except DeviceSetupCodeError as exc:
            raise DeviceClaimError(exc.code, exc.message) from exc

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
    if requires_setup:
        device.device_category = category
        device.user_label = label
        reset_setup_code_failure_state(device)

    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="claim",
        actor_account_user_id=account_user_id,
        health_subject_id=health_subject_id,
        gateway_install_id=gateway_install_id,
        detail={
            "binding_id": binding.id,
            "setup_code_used": requires_setup,
            "device_category": category if requires_setup else None,
            "user_label_set": bool(label) if requires_setup else False,
        },
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
