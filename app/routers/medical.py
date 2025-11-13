# app/routers/medical.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo

router = APIRouter()


@router.post("/share", response_model=APIResponse)
def share_medical_data(payload: dict, db: Session = Depends(get_db)):
    """
    اشتراک داده سلامت با پزشک یا سیستم دیگر
    {
      "user_id": 1,
      "doctor_id": 101,
      "duration": 48  # مدت زمان مجاز اشتراک (ساعت)
    }
    """
    user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    expiry = datetime.utcnow() + timedelta(hours=payload.get("duration", 24))
    token = f"MED-{user.id}-{int(datetime.utcnow().timestamp())}"

    share_info = {
        "user_id": user.id,
        "doctor_id": payload.get("doctor_id"),
        "access_token": token,
        "valid_until": expiry.isoformat()
    }

    # در نسخه بعدی می‌تونیم این رو در جدول جدا ذخیره کنیم
    return APIResponse(ok=True, data=share_info)


@router.get("/records", response_model=APIResponse)
def get_medical_records(user_id: int, db: Session = Depends(get_db)):
    """
    دریافت پرونده سلامت خلاصه‌شده کاربر
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    latest_health = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == user_id)
        .order_by(models.HealthData.created_at.desc())
        .first()
    )
    latest_lifestyle = (
        db.query(models.LifestyleData)
        .filter(models.LifestyleData.user_id == user_id)
        .order_by(models.LifestyleData.created_at.desc())
        .first()
    )

    record = {
        "user": {"id": user.id, "name": user.name, "phone": user.phone},
        "last_health": {
            "heart_rate": getattr(latest_health, "heart_rate", None),
            "spo2": getattr(latest_health, "spo2", None),
            "temperature": getattr(latest_health, "temperature", None),
            "created_at": getattr(latest_health, "created_at", None),
        },
        "last_lifestyle": {
            "steps": getattr(latest_lifestyle, "steps", None),
            "sleep_hours": getattr(latest_lifestyle, "sleep_hours", None),
            "stress_level": getattr(latest_lifestyle, "stress_level", None),
        },
    }

    return APIResponse(ok=True, data=record)


@router.post("/doctor-note", response_model=APIResponse)
def add_doctor_note(payload: dict, db: Session = Depends(get_db)):
    """
    ثبت یادداشت پزشک برای کاربر
    {
      "user_id": 1,
      "doctor_name": "Dr. Rahimi",
      "note": "Continue daily walking and measure blood pressure regularly."
    }
    """
    user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    msg = f"Note from {payload.get('doctor_name')}: {payload.get('note')}"

    notif = models.Notification(
        user_id=user.id,
        type="doctor_note",
        title="یادداشت پزشک",
        message=msg,
        priority=2,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()

    return APIResponse(ok=True, data={"note_added": True})
