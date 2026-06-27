# app/routers/devices.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.database import get_db
from backend.app.models import Device, User
from backend.app.core.device_auth import generate_device_token, hash_device_token
from backend.app.schemas.devices import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DevicesListResponse,
)
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()


def _reject_legacy_user_id_query(request: Request) -> None:
    """Reject legacy user_id query param; identity comes from JWT only."""
    if request.query_params.get("user_id") is not None:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "extra_forbidden",
                    "loc": ["query", "user_id"],
                    "msg": "Extra inputs are not permitted",
                    "input": request.query_params.get("user_id"),
                }
            ],
        )


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(
    body: DeviceRegisterRequest,
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Register a device for the authenticated user. Returns plaintext token once."""
    user_id = auth_user.id

    existing = db.query(Device).filter(Device.device_id == body.device_id).first()
    if existing:
        if existing.user_id != user_id:
            return DeviceRegisterResponse(
                ok=False,
                error={"code": "DEVICE_ID_TAKEN", "message": "device_id is already registered to another user"},
            )
        token = generate_device_token()
        existing.token_hash = hash_device_token(token)
        existing.status = "active"
        existing.revoked_at = None
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return DeviceRegisterResponse(ok=True, data={"device_id": existing.device_id, "token": token, "rotated": True})

    token = generate_device_token()
    device = Device(
        user_id=user_id,
        device_id=body.device_id,
        device_type=body.device_type or "heart_rate",
        status="active",
        token_hash=hash_device_token(token),
        created_at=datetime.utcnow(),
        revoked_at=None,
        last_seen_at=None,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceRegisterResponse(ok=True, data={"device_id": device.device_id, "token": token})


@router.get("", response_model=DevicesListResponse)
def list_devices(
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """List devices owned by the authenticated user."""
    user_id = auth_user.id
    devices = db.query(Device).filter(Device.user_id == user_id).order_by(Device.id.desc()).all()
    data = []
    for d in devices:
        data.append(
            {
                "device_id": d.device_id,
                "device_type": d.device_type,
                "status": d.status,
                "last_seen_at": d.last_seen_at,
                "created_at": d.created_at,
                "revoked_at": d.revoked_at,
            }
        )
    return DevicesListResponse(ok=True, data={"devices": data, "count": len(data)})


@router.post("/{device_id}/revoke", response_model=DeviceRegisterResponse)
def revoke_device(
    device_id: str,
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Revoke a device owned by the authenticated user."""
    user_id = auth_user.id
    device = db.query(Device).filter(Device.device_id == device_id, Device.user_id == user_id).first()
    if not device:
        return DeviceRegisterResponse(ok=False, error={"code": "DEVICE_NOT_FOUND", "message": "Device not found"})

    device.status = "revoked"
    device.revoked_at = datetime.utcnow()
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceRegisterResponse(ok=True, data={"device_id": device.device_id, "status": device.status})


@router.post("/{device_id}/rotate-token", response_model=DeviceRegisterResponse)
def rotate_device_token(
    device_id: str,
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Rotate device token for a device owned by the authenticated user."""
    user_id = auth_user.id
    device = db.query(Device).filter(Device.device_id == device_id, Device.user_id == user_id).first()
    if not device:
        return DeviceRegisterResponse(ok=False, error={"code": "DEVICE_NOT_FOUND", "message": "Device not found"})

    token = generate_device_token()
    device.token_hash = hash_device_token(token)
    device.status = "active"
    device.revoked_at = None
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceRegisterResponse(ok=True, data={"device_id": device.device_id, "token": token})
