# app/routers/device.py
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo, ApiResponseV1
from backend.app.services.notification_engine import DecisionEngine
from backend.app.schemas.device import (
    DeviceIngestRequest,
    DeviceIngestResponse,
    DeviceHeartbeatRequest,
    DeviceAcknowledgeRequest,
)
from backend.app.services.device_ingestion import ingest_event, DeviceRateLimitExceeded
from backend.app.core.device_auth import (
    get_device_token,
    authorize_device_or_legacy,
    authorize_operational_device,
    reject_legacy_user_id_query,
)
from backend.app.services.vitals.vital_registry import VitalValidationError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/pending-commands", response_model=ApiResponseV1)
def get_pending_commands(
    device_id: str = Query(..., description="Logical device id"),
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
    _: None = Depends(reject_legacy_user_id_query),
):
    """
    Fetch pending audio commands for the device's owner.

    Requires X-DEVICE-TOKEN and device_id query. user_id is derived from the device row.
    """
    device = authorize_operational_device(db=db, device_id=device_id, token=token)
    user_id = device.user_id

    alerts = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .filter(models.Notification.is_read == False)
        .filter(models.Notification.priority.in_(["high", "critical"]))
        .order_by(models.Notification.created_at.desc())
        .all()
    )

    if not alerts:
        return APIResponse(ok=True, data={"commands": []})

    def priority_to_numeric(priority_str: str) -> int:
        priority_map = {"low": 1, "normal": 2, "high": 3, "critical": 4}
        return priority_map.get(priority_str, 2)

    commands = []
    for a in alerts:
        priority_num = priority_to_numeric(a.priority)
        command = {
            "sound_id": "alert_default",
            "text": a.body or a.title or "Health Alert",
            "volume": 90,
            "repeat": 2 if priority_num >= 3 else 1,
            "language": "fa",
            "priority": priority_num,
        }
        commands.append(command)
        a.is_read = True

    db.commit()
    return APIResponse(ok=True, data={"commands": commands})


@router.post("/heartbeat", response_model=ApiResponseV1)
def device_heartbeat(
    body: DeviceHeartbeatRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Device heartbeat. Requires X-DEVICE-TOKEN; user_id is derived from the device row.
    """
    device = authorize_operational_device(db=db, device_id=body.device_id, token=token)

    now = datetime.utcnow()
    device.last_seen_at = now

    if body.status is not None:
        device.status = str(body.status)

    db.commit()
    db.refresh(device)

    logger.info(
        "[DEVICE_HEARTBEAT] Updated device_id=%s user_id=%s last_seen_at=%s status=%s",
        device.device_id,
        device.user_id,
        device.last_seen_at,
        device.status,
    )

    return APIResponse(ok=True, data={"message": "Heartbeat received successfully."})


@router.post("/acknowledge", response_model=ApiResponseV1)
def acknowledge_command(
    body: DeviceAcknowledgeRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Acknowledge audio command playback. Requires X-DEVICE-TOKEN; user_id from device row.
    """
    device = authorize_operational_device(db=db, device_id=body.device_id, token=token)

    decision_engine = DecisionEngine(db)
    decision_engine.create_insight_notification(
        user_id=device.user_id,
        insight_text=f"Sound '{body.sound_id}' executed with status: {body.status}",
        priority="low",
    )

    return APIResponse(ok=True, data={"acknowledged": True})


@router.post("/ingest", response_model=DeviceIngestResponse)
def ingest_device_event(
    request: DeviceIngestRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Ingest device event (vital signs) with deduplication and memory mapping.

    Requires X-DEVICE-TOKEN header.

    Auth modes (Release C2):
    - DEVICE_AUTH_MODE=legacy_only: validate shared DEVICE_INGEST_TOKEN (C1 behavior)
    - DEVICE_AUTH_MODE=db_only: validate per-device token from DB (requires request.device_id)
    - DEVICE_AUTH_MODE=hybrid (default): try DB first, then legacy if enabled
    """
    try:
        _auth_result, device = authorize_device_or_legacy(
            db=db,
            user_id=request.user_id,
            device_id=request.device_id,
            token=token,
        )

        effective_user_id = request.user_id
        if device is not None:
            if request.user_id != device.user_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="user_id does not match device owner",
                )
            request.device_id = device.device_id
            effective_user_id = device.user_id

        user = db.query(models.User).filter(models.User.id == effective_user_id).first()
        if not user:
            return DeviceIngestResponse(
                ok=False,
                error={"code": "USER_NOT_FOUND", "message": "User not found"},
            )

        if not request.payload:
            return DeviceIngestResponse(
                ok=False,
                error={"code": "INVALID_PAYLOAD", "message": "Payload must not be empty"},
            )

        trace_id = http_request.headers.get("X-TRACE-ID") or uuid.uuid4().hex
        event, dedupe_key, result = ingest_event(
            db=db,
            user_id=effective_user_id,
            event_type=request.event_type,
            payload=request.payload,
            device_id=request.device_id,
            recorded_at=request.recorded_at,
            trace_id=trace_id,
        )

        if event is None:
            return DeviceIngestResponse(
                ok=True,
                data={
                    "event_id": None,
                    "dedupe_key": dedupe_key,
                    "message": "Event already exists (duplicate)",
                    **result,
                },
            )

        return DeviceIngestResponse(
            ok=True,
            data={
                "event_id": event.id,
                "dedupe_key": dedupe_key,
                **result,
            },
        )

    except ValueError as e:
        return DeviceIngestResponse(
            ok=False,
            error={"code": "VALIDATION_ERROR", "message": str(e)},
        )

    except VitalValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    except DeviceRateLimitExceeded as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    except HTTPException as e:
        logger.debug("[DEVICE_INGEST] Re-raising HTTPException status_code=%s", e.status_code)
        raise

    except Exception:
        logger.exception("Failed to ingest event")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "code": "INTERNAL_ERROR", "message": "Failed to ingest event"},
        )
