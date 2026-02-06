# app/routers/ai_core.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.core.ai_text_engine import generate_notification_text
from app.services.notification_engine import DecisionEngine

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
        user_name=None,  # Name no longer stored in database
        language=user.preferred_language or "en",
        context={
            "heart_rate": avg_hr,
            "temperature": avg_temp,
            "spo2": avg_spo2,
            "mood": mood_state,
        },
    )

    # Extract message from notification data (handle both old and new formats)
    notif_message = notif_data.get("message", "Health analysis completed")
    
    # Use DecisionEngine instead of direct Notification creation
    decision_engine = DecisionEngine(db)
    notif = decision_engine.create_insight_notification(
        user_id=user.id,
        insight_text=notif_message,
        priority="normal"
    )

    # ثبت در حافظه‌ی صدی
    memory = models.Memory(
        user_id=user.id,
        user_message=f"Health analyzed: HR={round(avg_hr,1)}, Temp={round(avg_temp,1)}, SpO2={round(avg_spo2,1)}",
        sedi_response=notif_message,
        language=user.preferred_language or "en",
        created_at=datetime.utcnow(),
    )
    db.add(memory)
    db.commit()

    print(f"[AI CORE] Notification created for user_id={user.id}: {notif.body}")

    return APIResponse(
        ok=True,
        data={
            "user_id": user.id,
            "language": user.preferred_language,
            "notification": {
                "id": notif.id,
                "type": notif.type,
                "title": notif.title,
                "body": notif.body,
                "priority": notif.priority
            }
        },
    )
