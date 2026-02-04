# app/routers/device.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.services.notification_engine import DecisionEngine
from app.schemas.device import DeviceIngestRequest, DeviceIngestResponse
from app.services.device_ingestion import ingest_event
from app.core.device_auth import verify_device_token

router = APIRouter()


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
    {
        "device_id": "Sedi001",
        "user_id": 1,
        "battery": 92,
        "temperature": 41.3,
        "status": "active"
    }
    """
    user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not user:
        return APIResponse(
            ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )

    msg = (
        f"Device {payload.get('device_id')} heartbeat received. "
        f"Battery={payload.get('battery')}%, Temp={payload.get('temperature')}°C"
    )

    # Use DecisionEngine instead of direct Notification creation
    decision_engine = DecisionEngine(db)
    notif = decision_engine.create_insight_notification(
        user_id=user.id,
        insight_text=msg,
        priority="low"
    )

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
    _token: str = Depends(verify_device_token)
):
    """
    Ingest device event (vital signs) with deduplication and memory mapping.
    
    Requires X-DEVICE-TOKEN header matching DEVICE_INGEST_TOKEN environment variable.
    
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
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[DEVICE_INGEST] Endpoint error: {e}", exc_info=True)
        return DeviceIngestResponse(
            ok=False,
            error={"code": "INTERNAL_ERROR", "message": "Failed to ingest event"}
        )
