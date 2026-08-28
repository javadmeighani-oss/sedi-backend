# app/routers/devices.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.database import get_db
from backend.app.models import Device, User, HealthSubject
from backend.app.core.device_auth import generate_device_token, hash_device_token
from backend.app.schemas.devices import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DevicesListResponse,
    HubStatusResponse,
)
from backend.app.schemas.health_subject import DeviceRebindRequest
from backend.app.routers.auth_otp import get_current_user
from backend.app.services.gate1_access import caregiver_can_manage_dependent
from backend.app.services.gate5.gadget_hub_status import (
    GADGET_HUB_DEVICE_TYPE,
    find_active_gadget_hub_for_user,
    build_hub_status_payload,
)
from backend.app.services.i9.device_binding_service import bind_device_to_subject, rebind_device
from backend.app.services.i9.health_subject_service import (
    account_can_access_subject,
    ensure_self_subject_for_account,
)

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


def _resolve_registration_health_subject(
    db: Session,
    *,
    account_user_id: int,
    body: DeviceRegisterRequest,
) -> int:
    """Resolve target health subject for device binding."""
    if body.health_subject_id is not None:
        if not account_can_access_subject(db, account_user_id, body.health_subject_id):
            raise HTTPException(status_code=403, detail="HEALTH_SUBJECT_ACCESS_DENIED")
        return body.health_subject_id

    if body.subject_user_id is not None and body.subject_user_id != account_user_id:
        if not caregiver_can_manage_dependent(db, account_user_id, body.subject_user_id, require_device=True):
            raise HTTPException(status_code=403, detail="DEVICE_SUBJECT_FORBIDDEN")
        legacy = ensure_self_subject_for_account(db, body.subject_user_id, commit=False)
        return legacy.id

    self_subject = ensure_self_subject_for_account(db, account_user_id, commit=False)
    return self_subject.id


def _legacy_subject_user_id(
    db: Session,
    *,
    body: DeviceRegisterRequest,
    account_user_id: int,
    health_subject_id: int,
) -> int | None:
    """Transitional legacy field: mirror linked user when present."""
    if body.subject_user_id is not None:
        return body.subject_user_id
    hs = db.query(HealthSubject).filter(HealthSubject.id == health_subject_id).first()
    if hs is not None and hs.linked_user_id is not None:
        return hs.linked_user_id
    return account_user_id


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(
    body: DeviceRegisterRequest,
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Register a device for the authenticated user. Returns plaintext token once."""
    user_id = auth_user.id
    requested_type = (body.device_type or "heart_rate").strip()

    try:
        health_subject_id = _resolve_registration_health_subject(db, account_user_id=user_id, body=body)
    except HTTPException as exc:
        code = exc.detail if isinstance(exc.detail, str) else "DEVICE_SUBJECT_FORBIDDEN"
        return DeviceRegisterResponse(ok=False, error={"code": code, "message": str(exc.detail)})

    if requested_type == GADGET_HUB_DEVICE_TYPE:
        active_hub = find_active_gadget_hub_for_user(db, user_id)
        if active_hub is not None and active_hub.device_id != body.device_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "GADGET_HUB_ALREADY_REGISTERED",
                    "message": "User already has an active Gadget Hub",
                    "existing_device_id": active_hub.device_id,
                },
            )

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
        existing.subject_user_id = _legacy_subject_user_id(
            db, body=body, account_user_id=user_id, health_subject_id=health_subject_id
        )
        bind_device_to_subject(
            db,
            device=existing,
            health_subject_id=health_subject_id,
            bound_by_account_user_id=user_id,
            commit=False,
        )
        db.commit()
        db.refresh(existing)
        return DeviceRegisterResponse(
            ok=True,
            data={
                "device_id": existing.device_id,
                "token": token,
                "rotated": True,
                "health_subject_id": existing.health_subject_id,
                "subject_user_id": existing.subject_user_id,
            },
        )

    token = generate_device_token()
    legacy_subject_id = _legacy_subject_user_id(
        db, body=body, account_user_id=user_id, health_subject_id=health_subject_id
    )
    device = Device(
        user_id=user_id,
        subject_user_id=legacy_subject_id,
        device_id=body.device_id,
        device_type=requested_type or "heart_rate",
        status="active",
        token_hash=hash_device_token(token),
        created_at=datetime.utcnow(),
        revoked_at=None,
        last_seen_at=None,
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(
        db,
        device=device,
        health_subject_id=health_subject_id,
        bound_by_account_user_id=user_id,
        commit=False,
    )
    db.commit()
    db.refresh(device)
    return DeviceRegisterResponse(
        ok=True,
        data={
            "device_id": device.device_id,
            "token": token,
            "health_subject_id": device.health_subject_id,
            "subject_user_id": device.subject_user_id,
        },
    )


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
                "health_subject_id": d.health_subject_id,
                "subject_user_id": d.subject_user_id or d.user_id,
                "last_seen_at": d.last_seen_at,
                "created_at": d.created_at,
                "revoked_at": d.revoked_at,
            }
        )
    return DevicesListResponse(ok=True, data={"devices": data, "count": len(data)})


@router.get("/hub-status", response_model=HubStatusResponse)
def get_gadget_hub_status(
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Return Gadget Hub operational status and registered sensors for the authenticated user."""
    payload = build_hub_status_payload(db, auth_user.id)
    return HubStatusResponse(ok=True, data=payload)


@router.post("/{device_id}/rebind", response_model=DeviceRegisterResponse)
def rebind_device_route(
    device_id: str,
    body: DeviceRebindRequest,
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Rebind device to a different health subject; historical data stays on prior binding."""
    device = db.query(Device).filter(Device.device_id == device_id, Device.user_id == auth_user.id).first()
    if not device:
        return DeviceRegisterResponse(ok=False, error={"code": "DEVICE_NOT_FOUND", "message": "Device not found"})
    if not account_can_access_subject(db, auth_user.id, body.health_subject_id):
        return DeviceRegisterResponse(
            ok=False,
            error={"code": "HEALTH_SUBJECT_ACCESS_DENIED", "message": "Not allowed for this health subject"},
        )
    binding, _prior = rebind_device(
        db,
        device=device,
        new_health_subject_id=body.health_subject_id,
        bound_by_account_user_id=auth_user.id,
    )
    return DeviceRegisterResponse(
        ok=True,
        data={
            "device_id": device.device_id,
            "health_subject_id": device.health_subject_id,
            "binding_id": binding.id,
        },
    )


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
