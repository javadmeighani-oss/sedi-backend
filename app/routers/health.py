# app/routers/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.core.ai_text_engine import generate_notification_text

router = APIRouter()


@router.post("/add", response_model=APIResponse)
def add_health_data(payload: dict, db: Session = Depends(get_db)):
    """
    افزودن داده سلامت و تولید نوتیف هوشمند
    {
        "user_id": 1,
        "heart_rate": 98,
        "temperature": 37.6,
        "spo2": 95
    }
    """

    user_id = payload.get("user_id")
    if not user_id:
        return APIResponse(ok=False, error=ErrorInfo(code="MISSING_USER", message="user_id is required."))

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    # ذخیره داده سلامت
    data = models.HealthData(
        user_id=user_id,
        heart_rate=payload.get("heart_rate"),
        temperature=payload.get("temperature"),
        spo2=payload.get("spo2"),
        created_at=datetime.utcnow()
    )
    db.add(data)
    db.commit()
    db.refresh(data)

    # تولید متن هوشمند با توجه به وضعیت سلامت
    msg = generate_notification_text(
        user_name=user.name,
        language=user.preferred_language or "en",
        context={
            "heart_rate": data.heart_rate,
            "temperature": data.temperature,
            "spo2": data.spo2
        }
    )

    # ثبت نوتیف جدید
    notif = models.Notification(
        user_id=user.id,
        type="alert",
        title="Health Update",
        message=msg,
        priority=3,
        sound_id="alert_health",
        language=user.preferred_language or "en",
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    print(f"[HEALTH] New health data saved for {user.name or user.phone}")
    print(f"[NOTIF] {msg}")

    return APIResponse(
        ok=True,
        data={
            "user_id": user.id,
            "health_id": data.id,
            "notification_id": notif.id,
            "message": msg
        }
    )
