# app/routers/data.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo

router = APIRouter()


def create_auto_notification(db: Session, user_id: int, title: str, message: str, priority: int = 2):
    """ساخت خودکار اعلان در صورت تشخیص وضعیت غیرعادی"""
    notif = models.Notification(
        user_id=user_id,
        type="alert",
        title=title,
        message=message,
        priority=priority,
        sound_id="alert_health",
        language="fa",
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()


@router.post("/upload", response_model=APIResponse)
def upload_data(payload: dict, db: Session = Depends(get_db)):
    """
    دریافت داده از گجت یا اپلیکیشن
    {
        "user_id": 1,
        "source": "device",
        "type": "health",
        "data": { "heart_rate": 110, "spo2": 90, "temperature": 38.2 }
    }
    """

    user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    data_type = payload.get("type")

    if data_type == "health":
        data = payload.get("data", {})

        record = models.HealthData(
            user_id=user.id,
            source=payload.get("source", "device"),
            heart_rate=data.get("heart_rate"),
            spo2=data.get("spo2"),
            systolic=data.get("systolic"),
            diastolic=data.get("diastolic"),
            temperature=data.get("temperature"),
            created_at=datetime.utcnow(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # 🔹 تشخیص وضعیت‌های غیرطبیعی و ساخت اعلان خودکار
        alerts = []
        if record.heart_rate and record.heart_rate > 100:
            alerts.append(("ضربان قلب بالا", f"ضربان قلب {int(record.heart_rate)} bpm ثبت شد."))

        if record.spo2 and record.spo2 < 93:
            alerts.append(("کاهش اکسیژن خون", f"میزان SpO2 برابر {int(record.spo2)}٪ است."))

        if record.temperature and record.temperature > 37.8:
            alerts.append(("افزایش دمای بدن", f"دمای بدن {record.temperature}°C است."))

        # ایجاد اعلان‌ها
        for title, msg in alerts:
            create_auto_notification(db, user.id, title, msg, priority=3)

        return APIResponse(ok=True, data={"record_id": record.id, "alerts_generated": len(alerts)})

    elif data_type == "lifestyle":
        data = payload.get("data", {})
        record = models.LifestyleData(
            user_id=user.id,
            sleep_hours=data.get("sleep_hours"),
            steps=data.get("steps"),
            calories=data.get("calories"),
            stress_level=data.get("stress_level"),
            created_at=datetime.utcnow(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return APIResponse(ok=True, data={"record_id": record.id})

    else:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="INVALID_TYPE", message="Data type must be 'health' or 'lifestyle'."),
        )
