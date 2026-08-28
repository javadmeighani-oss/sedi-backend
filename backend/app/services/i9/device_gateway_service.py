"""Mobile gateway authorization — relay only, never data owner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.device_lifecycle_service import record_lifecycle_audit


class DeviceGatewayError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_active_gateway_authorization(
    db: Session,
    *,
    device_row_id: int,
    gateway_install_id: str,
) -> Optional[models.DeviceMobileGatewayAuthorization]:
    return (
        db.query(models.DeviceMobileGatewayAuthorization)
        .filter(
            models.DeviceMobileGatewayAuthorization.device_row_id == device_row_id,
            models.DeviceMobileGatewayAuthorization.gateway_install_id == gateway_install_id,
            models.DeviceMobileGatewayAuthorization.is_active.is_(True),
            models.DeviceMobileGatewayAuthorization.revoked_at.is_(None),
        )
        .first()
    )


def authorize_mobile_gateway(
    db: Session,
    *,
    device: models.Device,
    gateway_install_id: str,
    account_user_id: int,
    commit: bool = True,
) -> models.DeviceMobileGatewayAuthorization:
    """Pair/re-pair gateway; does not change Device↔HealthSubject binding."""
    gateway_install_id = gateway_install_id.strip()
    if not gateway_install_id:
        raise DeviceGatewayError("GATEWAY_ID_REQUIRED", "gateway_install_id is required")

    existing = get_active_gateway_authorization(
        db, device_row_id=device.id, gateway_install_id=gateway_install_id
    )
    if existing is not None:
        return existing

    now = utc_now()
    row = models.DeviceMobileGatewayAuthorization(
        device_row_id=device.id,
        gateway_install_id=gateway_install_id,
        authorized_by_account_user_id=account_user_id,
        authorized_at=now,
        is_active=True,
    )
    db.add(row)
    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="gateway_pair",
        actor_account_user_id=account_user_id,
        gateway_install_id=gateway_install_id,
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def disconnect_mobile_gateway(
    db: Session,
    *,
    device: models.Device,
    gateway_install_id: str,
    account_user_id: int,
    commit: bool = True,
) -> bool:
    """Disconnect gateway only; Device↔HealthSubject binding unchanged."""
    row = get_active_gateway_authorization(
        db, device_row_id=device.id, gateway_install_id=gateway_install_id.strip()
    )
    if row is None:
        return False
    now = utc_now()
    row.is_active = False
    row.revoked_at = now
    db.add(row)
    record_lifecycle_audit(
        db,
        device_row_id=device.id,
        operation="gateway_disconnect",
        actor_account_user_id=account_user_id,
        gateway_install_id=gateway_install_id.strip(),
        commit=False,
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return True


def list_active_gateways(db: Session, device_row_id: int) -> List[models.DeviceMobileGatewayAuthorization]:
    return (
        db.query(models.DeviceMobileGatewayAuthorization)
        .filter(
            models.DeviceMobileGatewayAuthorization.device_row_id == device_row_id,
            models.DeviceMobileGatewayAuthorization.is_active.is_(True),
            models.DeviceMobileGatewayAuthorization.revoked_at.is_(None),
        )
        .order_by(models.DeviceMobileGatewayAuthorization.authorized_at.desc())
        .all()
    )
