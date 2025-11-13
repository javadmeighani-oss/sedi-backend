# app/routers/notifications.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.core.ai_text_engine import generate_notification_text

router = APIRouter()


# ------------------ دریافت لیست نوتیف‌ها ------------------
@router.get("/", response_model=APIResponse)
def get_notifications(user_id: int, db: Session = Depends(get_db)):
    """
    دریافت آخرین نوتیف‌ها برای کاربر
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    notifs = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .order_by(models.Notification.created_at.desc())
        .limit(20)
        .all()
    )

    data = [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "tone": n.tone,
            "feedback_options": n.feedback_options,
            "language": n.language,
            "is_read": n.is_read,
            "created_at": n.created_at,
        }
        for n in notifs
    ]

    return APIResponse(ok=True, data={"notifications": data})


# ------------------ ساخت نوتیف جدید ------------------
@router.post("/create", response_model=APIResponse)
def create_notification(user_id: int, db: Session = Depends(get_db)):
    """
    ساخت نوتیف هوشمند برای کاربر بر اساس داده‌های اخیر سلامت یا تعامل
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    # داده‌های اخیر کاربر
    health = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == user_id)
        .order_by(models.HealthData.created_at.desc())
        .first()
    )
    mood = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user_id)
        .order_by(models.Memory.created_at.desc())
        .first()
    )

    context = {
        "heart_rate": health.heart_rate if health else None,
        "temperature": health.temperature if health else None,
        "spo2": health.spo2 if health else None,
        "mood": mood.mood if mood else "neutral"
    }

    notif_data = generate_notification_text(
        user_name=user.name,
        language=user.preferred_language or "en",
        context=context
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

    return APIResponse(ok=True, data={
        "id": notif.id,
        "message": notif.message,
        "tone": notif.tone,
        "feedback_options": notif.feedback_options,
        "language": notif.language
    })


# ------------------ ثبت واکنش کاربر ------------------
@router.post("/react", response_model=APIResponse)
def react_to_notification(notification_id: int, reaction: str, feedback: str = None, db: Session = Depends(get_db)):
    """
    واکنش به نوتیف:
    reaction = 'seen' | 'interact' | 'dislike'
    اگر reaction='dislike' → بازخورد در حافظه ذخیره می‌شود
    """
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not notif:
        return APIResponse(ok=False, error=ErrorInfo(code="NOT_FOUND", message="Notification not found."))

    user = db.query(models.User).filter(models.User.id == notif.user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    # واکنش دیده شد ✅
    if reaction == "seen":
        notif.is_read = True
        db.commit()
        return APIResponse(ok=True, data={"reaction": "seen", "message": "Notification marked as seen."})

    # تعامل با صدی 💬
    elif reaction == "interact":
        reply = {
            "en": f"{user.name}, I'm ready to talk whenever you are 🌿",
            "fa": f"{user.name}، هر وقت خواستی باهام صحبت کن 🌿",
            "ar": f"{user.name}، أنا جاهز للتحدث متى ما أردت 🌿"
        }
        return APIResponse(ok=True, data={"reaction": "interact", "message": reply.get(user.preferred_language, reply["en"])})

    # بازخورد منفی 👎
    elif reaction == "dislike":
        mem = models.Memory(
            user_id=user.id,
            summary=f"User feedback on notif {notif.id}: {feedback or 'No text'}",
            mood="negative",
            context="feedback_notification",
            created_at=datetime.utcnow(),
            last_interaction=datetime.utcnow()
        )
        db.add(mem)
        db.commit()
        return APIResponse(ok=True, data={
            "reaction": "dislike",
            "feedback_saved": True,
            "user_feedback": feedback or ""
        })

    else:
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_REACTION", message="Invalid reaction type."))
