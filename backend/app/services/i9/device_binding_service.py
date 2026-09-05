"""Device-to-Health-Subject historical binding."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models


class DeviceBindingError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_active_binding(
    db: Session,
    device_row_id: int,
    *,
    at_time: Optional[datetime] = None,
) -> Optional[models.DeviceSubjectBinding]:
    """Return binding active at at_time (default: now)."""
    ref = at_time or utc_now()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return (
        db.query(models.DeviceSubjectBinding)
        .filter(
            models.DeviceSubjectBinding.device_row_id == device_row_id,
            models.DeviceSubjectBinding.bound_at <= ref,
            (
                (models.DeviceSubjectBinding.unbound_at.is_(None))
                | (models.DeviceSubjectBinding.unbound_at > ref)
            ),
        )
        .order_by(models.DeviceSubjectBinding.bound_at.desc())
        .first()
    )


def bind_device_to_subject(
    db: Session,
    *,
    device: models.Device,
    health_subject_id: int,
    bound_by_account_user_id: Optional[int],
    bound_at: Optional[datetime] = None,
    commit: bool = True,
) -> models.DeviceSubjectBinding:
    """Create active binding; ends any prior active binding on the device."""
    now = bound_at or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Close any currently-open row (unbound_at IS NULL) so the partial unique
    # index uq_dsb_device_active_binding cannot be violated when bound_at is
    # historical relative to wall-clock prior bindings.
    open_binding = (
        db.query(models.DeviceSubjectBinding)
        .filter(
            models.DeviceSubjectBinding.device_row_id == device.id,
            models.DeviceSubjectBinding.unbound_at.is_(None),
        )
        .order_by(models.DeviceSubjectBinding.bound_at.desc())
        .first()
    )
    if open_binding is not None and open_binding.health_subject_id == health_subject_id:
        device.health_subject_id = health_subject_id
        device.current_binding_id = open_binding.id
        if commit:
            db.commit()
        return open_binding

    if open_binding is not None:
        close_at = now
        if open_binding.bound_at is not None and close_at < open_binding.bound_at:
            close_at = open_binding.bound_at
        open_binding.unbound_at = close_at
        db.add(open_binding)

    binding = models.DeviceSubjectBinding(
        device_row_id=device.id,
        health_subject_id=health_subject_id,
        bound_at=now,
        bound_by_account_user_id=bound_by_account_user_id,
    )
    db.add(binding)
    db.flush()
    device.health_subject_id = health_subject_id
    device.current_binding_id = binding.id
    if commit:
        db.commit()
        db.refresh(binding)
    else:
        db.flush()
    return binding


def rebind_device(
    db: Session,
    *,
    device: models.Device,
    new_health_subject_id: int,
    bound_by_account_user_id: Optional[int],
    bound_at: Optional[datetime] = None,
    commit: bool = True,
) -> Tuple[models.DeviceSubjectBinding, Optional[models.DeviceSubjectBinding]]:
    """Rebind device; historical observations retain prior binding attribution."""
    prior = get_active_binding(db, device.id)
    binding = bind_device_to_subject(
        db,
        device=device,
        health_subject_id=new_health_subject_id,
        bound_by_account_user_id=bound_by_account_user_id,
        bound_at=bound_at,
        commit=commit,
    )
    return binding, prior


def resolve_subject_for_device(
    db: Session,
    device: models.Device,
    *,
    measured_at: Optional[datetime] = None,
) -> Tuple[int, Optional[models.DeviceSubjectBinding]]:
    """Server-side subject resolution from binding history."""
    binding = get_active_binding(db, device.id, at_time=measured_at)
    if binding is None:
        if device.health_subject_id is not None:
            return device.health_subject_id, None
        raise DeviceBindingError("NO_ACTIVE_DEVICE_SUBJECT_BINDING")
    return binding.health_subject_id, binding
