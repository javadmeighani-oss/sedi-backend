# app/routers/ai_core.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.core.ai_text_engine import generate_notification_text

router = APIRouter()


@router.post("/analyze", response_model=APIResponse)
def analyze_health_data(user_id: int, db: Session = Depends(get_db)):
    """
    تحلیل داده‌های سلامت کاربر و ساخت نوتیف هوشمند چندزبانه
    """

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    # دریافت داده‌های اخیر سلامت
    health_data = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == user_id)
        .order_by(models.HealthData.created_at.desc())
        .limit(5)
        .all()
    )

    if not health_data:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_DATA", message="No health data found."))

    # میانگین مقادیر اخیر
    avg_hr = sum([d.heart_rate or 0 for d in health_data]) / len(health_data)
    avg_temp = sum([d.temperature or 0 for d in health_data]) / len(health_data)
    avg_spo2 = sum([d.spo2 or 0 for d in health_data]) / len(health_data)

    # خلق و خو از آخرین تعامل
    mood = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user_id)
        .order_by(models.Memory.created_at.desc())
        .first()
    )
    mood_state = mood.mood if mood else "neutral"

    # تولید نوتیف هوشمند از موتور زبانی
    notif_data = generate_notification_text(
        user_name=user.name,
        language=user.preferred_language or "en",
        context={
            "heart_rate": avg_hr,
            "temperature": avg_temp,
            "spo2": avg_spo2,
            "mood": mood_state,
        },
    )

    notif = models.Notification(
        user_id=user.id,
        type="alert",
        title="Health Update",
        message=notif_data["message"],
        tone=notif_data["tone"],
        feedback_options=notif_data["feedback_options"],
        language=user.preferred_language or "en",
        created_at=datetime.utcnow(),
    )

    db.add(notif)
    db.commit()
    db.refresh(notif)

    # ثبت در حافظه‌ی صدی
    memory = models.Memory(
        user_id=user.id,
        summary=f"Health analyzed: HR={round(avg_hr,1)}, Temp={round(avg_temp,1)}, SpO2={round(avg_spo2,1)}",
        mood=mood_state,
        context="auto_health_analysis",
        created_at=datetime.utcnow(),
        last_interaction=datetime.utcnow(),
    )
    db.add(memory)
    db.commit()

    print(f"[AI CORE] Notification created for {user.name}: {notif.message}")

    return APIResponse(
        ok=True,
        data={
            "user_id": user.id,
            "language": user.preferred_language,
            "notification": {
                "id": notif.id,
                "message": notif.message,
                "tone": notif.tone,
                "feedback_options": notif.feedback_options
            }
        },
    )
