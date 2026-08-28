"""Auditable device release, transfer, revoke lifecycle operations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.device_binding_service import bind_device_to_subject, get_active_binding
from backend.app.services.i9.device_credential_verifier import get_device_credential_verifier
from backend.app.services.i9.health_subject_service import account_can_access_subject


class DeviceLifecycleError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_lifecycle_audit(
    db: Session,
    *,
    device_row_id: int,
    operation: str,
    actor_account_user_id: Optional[int] = None,
    health_subject_id: Optional[int] = None,
    gateway_install_id: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    commit: bool = False,
) -> models.DeviceLifecycleAuditLog:
    row = models.DeviceLifecycleAuditLog(
        device_row_id=device_row_id,
        operation=operation,
        actor_account_user_id=actor_account_user_id,
        health_subject_id=health_subject_id,
        gateway_install_id=gateway_install_id,
        detail_json=json.dumps(detail) if detail else None,
        created_at=utc_now(),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def _assert_actor_can_manage_device(db: Session, device: models.Device, account_user_id: int) -> None:
    allowed = {device.owner_account_user_id, device.user_id}
    allowed.discard(None)
    if allowed and account_user_id not in allowed:
        raise DeviceLifecycleError("DEVICE_ACCESS_DENIED", "Account cannot manage this device")


def release_device(
    db: Session,
    *,
    device: models.Device,
    account_user_id: int,
    commit: bool = True,
) -> Optional[models.DeviceSubjectBinding]:
    """Close active binding; preserve historical data on prior subject."""
    _assert_actor_can_manage_device(db, device, account_user_id)
    active = get_active_binding(db, device.id)
    if active is None:
        raise DeviceLifecycleError("NO_ACTIVE_BINDING", "Device has no active health subject binding")

    now = utc_now()
    active.unbound_at = now
    db.add(active)
    device.health_subject_id = None
    device.current_binding_id = None
    device.claim_lifecycle_status = "released"

    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="release",
        actor_account_user_id=account_user_id,
        health_subject_id=active.health_subject_id,
        detail={"binding_id": active.id, "unbound_at": now.isoformat()},
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(active)
    else:
        db.flush()
    return active


def transfer_device(
    db: Session,
    *,
    device: models.Device,
    account_user_id: int,
    new_health_subject_id: int,
    possession_proof: str,
    commit: bool = True,
) -> models.DeviceSubjectBinding:
    """Transfer: end old binding, require proof, create new binding; old data stays."""
    _assert_actor_can_manage_device(db, device, account_user_id)
    if not account_can_access_subject(db, account_user_id, new_health_subject_id):
        raise DeviceLifecycleError("HEALTH_SUBJECT_ACCESS_DENIED", "Account cannot manage target health subject")

    verifier = get_device_credential_verifier()
    verification = verifier.verify(device, possession_proof)
    if not verification.verified:
        raise DeviceLifecycleError(
            verification.reject_reason or "POSSESSION_PROOF_FAILED",
            "Device possession proof required for transfer",
        )

    prior = get_active_binding(db, device.id)
    if prior is not None:
        now = utc_now()
        prior.unbound_at = now
        db.add(prior)
        record_lifecycle_audit(
            db,
            device_row_id=device.id,
            operation="transfer_end_prior_binding",
            actor_account_user_id=account_user_id,
            health_subject_id=prior.health_subject_id,
            detail={"binding_id": prior.id},
            commit=False,
        )

    binding = bind_device_to_subject(
        db,
        device=device,
        health_subject_id=new_health_subject_id,
        bound_by_account_user_id=account_user_id,
        commit=False,
    )
    device.claim_lifecycle_status = "claimed"
    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="transfer",
        actor_account_user_id=account_user_id,
        health_subject_id=new_health_subject_id,
        detail={"binding_id": binding.id, "prior_binding_id": prior.id if prior else None},
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(binding)
    else:
        db.flush()
    return binding


def revoke_device_lifecycle(
    db: Session,
    *,
    device: models.Device,
    account_user_id: int,
    commit: bool = True,
) -> models.Device:
    """Reject future device authentication; preserve history."""
    _assert_actor_can_manage_device(db, device, account_user_id)
    now = utc_now()
    device.status = "revoked"
    device.claim_lifecycle_status = "revoked"
    device.revoked_at = now
    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="revoke",
        actor_account_user_id=account_user_id,
        health_subject_id=device.health_subject_id,
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(device)
    else:
        db.flush()
    return device


def suspend_device(
    db: Session,
    *,
    device: models.Device,
    account_user_id: int,
    commit: bool = True,
) -> models.Device:
    _assert_actor_can_manage_device(db, device, account_user_id)
    device.claim_lifecycle_status = "suspended"
    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="suspend",
        actor_account_user_id=account_user_id,
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(device)
    else:
        db.flush()
    return device
