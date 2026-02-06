# app/routers/device.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.services.notification_engine import DecisionEngine
from app.schemas.device import DeviceIngestRequest, DeviceIngestResponse
from app.services.device_ingestion import ingest_event, DeviceRateLimitExceeded
from app.core.device_auth import get_device_token, authorize_device_or_legacy
from app.services.vitals.vital_registry import VitalValidationError

router = APIRouter()
logger = logging.getLogger(__name__)


# 🔹 1. دریافت فرمان‌های صوتی جدید برای گجت
@router.get("/pending-commands", response_model=APIResponse)
def get_pending_commands(user_id: int, db: Session = Depends(get_db)):
    """
    گجت فرمان‌های صوتی جدید را از این مسیر می‌گیرد
    """
    # Query high/critical priority notifications (priority is now a string)
    alerts = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .filter(models.Notification.is_read == False)
        .filter(models.Notification.priority.in_(["high", "critical"]))  # Updated: priority is now string
        .order_by(models.Notification.created_at.desc())
        .all()
    )

    if not alerts:
        return APIResponse(ok=True, data={"commands": []})

    # Helper function to convert string priority to numeric for comparison
    def priority_to_numeric(priority_str: str) -> int:
        priority_map = {"low": 1, "normal": 2, "high": 3, "critical": 4}
        return priority_map.get(priority_str, 2)
    
    commands = []
    for a in alerts:
        priority_num = priority_to_numeric(a.priority)
        command = {
            "sound_id": "alert_default",  # sound_id removed from new model
            "text": a.body or a.title or "هشدار سلامت",  # Updated: message -> body
            "volume": 90,
            "repeat": 2 if priority_num >= 3 else 1,
            "language": "fa",  # language removed from new model, using default
            "priority": priority_num,
        }
        commands.append(command)
        a.is_read = True

    db.commit()
    return APIResponse(ok=True, data={"commands": commands})


# 🔹 2. ارسال وضعیت گجت به سرور (Heartbeat)
@router.post("/heartbeat", response_model=APIResponse)
def device_heartbeat(payload: dict, db: Session = Depends(get_db)):
    """
    گجت هر چند ثانیه وضعیت خود را به سرور می‌فرستد.
    Updates device.last_seen_at in database.
    {
        "device_id": "Sedi001",
        "user_id": 1,
        "battery": 92,
        "temperature": 41.3,
        "status": "active"
    }
    """
    # Validate required fields
    user_id = payload.get("user_id")
    device_id = payload.get("device_id")
    
    if not user_id or not device_id:
        return APIResponse(
            ok=False,
            error=ErrorInfo(
                code="INVALID_PAYLOAD",
                message="Missing required fields: user_id and device_id are required."
            )
        )
    
    # Validate user exists
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    # Fetch device (must be active, not revoked)
    device = (
        db.query(models.Device)
        .filter(
            models.Device.device_id == device_id,
            models.Device.user_id == user_id,
            models.Device.revoked_at.is_(None)  # Only active devices
        )
        .first()
    )
    
    if not device:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="DEVICE_NOT_FOUND", message="Device not found or revoked.")
        )
    
    # Update device record
    now = datetime.utcnow()
    device.last_seen_at = now
    
    # Optionally update status if provided
    if payload.get("status") is not None:
        device.status = str(payload["status"])
    
    db.commit()
    db.refresh(device)
    
    logger.info(
        f"[DEVICE_HEARTBEAT] Updated device_id={device_id} user_id={user_id} "
        f"last_seen_at={device.last_seen_at} status={device.status}"
    )
    
    # Note: Removed notification creation to avoid spam from frequent heartbeats.
    # Notifications should only be created for critical events (low battery, errors, etc.)
    # which can be handled by other endpoints or scheduled checks.
    
    return APIResponse(ok=True, data={"message": "Heartbeat received successfully."})


# 🔹 3. تأیید اجرای فرمان توسط گجت (Acknowledge)
@router.post("/acknowledge", response_model=APIResponse)
def acknowledge_command(payload: dict, db: Session = Depends(get_db)):
    """
    گجت پس از اجرای فرمان صوتی، نتیجه را اعلام می‌کند.
    {
        "user_id": 1,
        "sound_id": "alert_temp",
        "status": "played"
    }
    """
    user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not user:
        return APIResponse(
            ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )

    # Use DecisionEngine instead of direct Notification creation
    decision_engine = DecisionEngine(db)
    notif = decision_engine.create_insight_notification(
        user_id=user.id,
        insight_text=f"Sound '{payload.get('sound_id')}' executed with status: {payload.get('status')}",
        priority="low"
    )

    return APIResponse(ok=True, data={"acknowledged": True})


# 🔹 4. Device Event Ingestion (Release C1)
@router.post("/ingest", response_model=DeviceIngestResponse)
def ingest_device_event(
    request: DeviceIngestRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token)
):
    """
    Ingest device event (vital signs) with deduplication and memory mapping.
    
    Requires X-DEVICE-TOKEN header.
    
    Auth modes (Release C2):
    - DEVICE_AUTH_MODE=legacy_only: validate shared DEVICE_INGEST_TOKEN (C1 behavior)
    - DEVICE_AUTH_MODE=db_only: validate per-device token from DB (requires request.device_id)
    - DEVICE_AUTH_MODE=hybrid (default): try DB first, then legacy if enabled
    
    Example:
    {
        "user_id": 1,
        "device_id": "Sedi001",
        "event_type": "heart_rate",
        "payload": {
            "bpm": 82,
            "quality": "good"
        },
        "recorded_at": "2026-02-02T10:30:00Z"
    }
    """
    try:
        # Authorize device (hybrid / db_only / legacy_only)
        _auth_result, device = authorize_device_or_legacy(
            db=db,
            user_id=request.user_id,
            device_id=request.device_id,
            token=token
        )
        # In DB-auth mode, trust registered device_id
        if device is not None:
            request.device_id = device.device_id

        # Validate user exists
        user = db.query(models.User).filter(models.User.id == request.user_id).first()
        if not user:
            return DeviceIngestResponse(
                ok=False,
                error={"code": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        # Validate payload is not empty
        if not request.payload:
            return DeviceIngestResponse(
                ok=False,
                error={"code": "INVALID_PAYLOAD", "message": "Payload must not be empty"}
            )
        
        # Ingest event
        event, dedupe_key = ingest_event(
            db=db,
            user_id=request.user_id,
            event_type=request.event_type,
            payload=request.payload,
            device_id=request.device_id,
            recorded_at=request.recorded_at
        )
        
        if event is None:
            # Duplicate event (already exists)
            return DeviceIngestResponse(
                ok=True,
                data={
                    "event_id": None,
                    "dedupe_key": dedupe_key,
                    "message": "Event already exists (duplicate)"
                }
            )
        
        return DeviceIngestResponse(
            ok=True,
            data={
                "event_id": event.id,
                "dedupe_key": dedupe_key
            }
        )
    
    except ValueError as e:
        return DeviceIngestResponse(
            ok=False,
            error={"code": "VALIDATION_ERROR", "message": str(e)}
        )

    except VitalValidationError as e:
        # Schema-driven validation errors -> 422
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    except DeviceRateLimitExceeded as e:
        # Return 429 (do not write to DB)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    except HTTPException as e:
        # Preserve correct HTTP status codes (e.g., 401/429/422). Do not swallow auth/validation exceptions.
        logger.debug("[DEVICE_INGEST] Re-raising HTTPException status_code=%s", e.status_code)
        raise

    except Exception as e:
        logger.exception("Failed to ingest event")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "code": "INTERNAL_ERROR", "message": "Failed to ingest event"},
        )
