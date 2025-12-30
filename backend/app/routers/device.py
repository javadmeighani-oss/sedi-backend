# app/routers/device.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo

router = APIRouter()


# 🔹 1. دریافت فرمان‌های صوتی جدید برای گجت
@router.get("/pending-commands", response_model=APIResponse)
def get_pending_commands(user_id: int, db: Session = Depends(get_db)):
    """
    گجت فرمان‌های صوتی جدید را از این مسیر می‌گیرد
    """
    alerts = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .filter(models.Notification.is_read == False)
        .filter(models.Notification.priority >= 3)
        .order_by(models.Notification.created_at.desc())
        .all()
    )

    if not alerts:
        return APIResponse(ok=True, data={"commands": []})

    commands = []
    for a in alerts:
        command = {
            "sound_id": a.sound_id or "alert_default",
            "text": a.message or a.title or "هشدار سلامت",
            "volume": 90,
            "repeat": 2 if a.priority >= 3 else 1,
            "language": a.language or "fa",
            "priority": a.priority,
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

    notif = models.Notification(
        user_id=user.id,
        type="info",
        title="Heartbeat",
        message=msg,
        priority=1,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()

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

    notif = models.Notification(
        user_id=user.id,
        type="log",
        title="Command acknowledged",
        message=f"Sound '{payload.get('sound_id')}' executed with status: {payload.get('status')}",
        priority=1,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()

    return APIResponse(ok=True, data={"acknowledged": True})
