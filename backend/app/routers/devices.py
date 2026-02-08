# app/routers/devices.py
from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter()


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(
    user_id: int,
    body: DeviceRegisterRequest,
    db: Session = Depends(get_db),
):
    # Ownership check by user_id param (no auth yet)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return DeviceRegisterResponse(ok=False, error={"code": "USER_NOT_FOUND", "message": "User not found"})

    # Ensure device_id not already registered to a different user
    existing = db.query(Device).filter(Device.device_id == body.device_id).first()
    if existing:
        if existing.user_id != user_id:
            return DeviceRegisterResponse(
                ok=False,
                error={"code": "DEVICE_ID_TAKEN", "message": "device_id is already registered to another user"},
            )
        # If same user, treat as rotate for simplicity (return new token once)
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
def list_devices(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return DevicesListResponse(ok=False, error={"code": "USER_NOT_FOUND", "message": "User not found"})

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
def revoke_device(device_id: str, user_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device or device.user_id != user_id:
        return DeviceRegisterResponse(ok=False, error={"code": "DEVICE_NOT_FOUND", "message": "Device not found"})

    device.status = "revoked"
    device.revoked_at = datetime.utcnow()
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceRegisterResponse(ok=True, data={"device_id": device.device_id, "status": device.status})


@router.post("/{device_id}/rotate-token", response_model=DeviceRegisterResponse)
def rotate_device_token(device_id: str, user_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device or device.user_id != user_id:
        return DeviceRegisterResponse(ok=False, error={"code": "DEVICE_NOT_FOUND", "message": "Device not found"})

    token = generate_device_token()
    device.token_hash = hash_device_token(token)
    device.status = "active"
    device.revoked_at = None
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceRegisterResponse(ok=True, data={"device_id": device.device_id, "token": token})

