# app/routers/device_data.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
import json

router = APIRouter()


@router.post("/data/upload", response_model=APIResponse)
def upload_device_data(payload: dict, db: Session = Depends(get_db)):
    """
    ثبت داده‌های سنسورهای گجت
    مثال:
    {
      "device_id": "Sedi001",
      "user_id": 1,
      "sensors": {
        "ecg": [0.12, 0.15, 0.13, 0.11],
        "ppg": [820, 830, 815, 805],
        "temperature": 36.9,
        "heart_rate": 82,
        "spo2": 97,
        "steps": 3456
      },
      "timestamp": "2025-11-06T10:05:23Z"
    }
    """
    user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    sensors = payload.get("sensors", {})
    created_at = datetime.utcnow()

    # ذخیره داده‌های حیاتی (HealthData)
    record_health = models.HealthData(
        user_id=user.id,
        source="device",
        heart_rate=sensors.get("heart_rate"),
        spo2=sensors.get("spo2"),
        temperature=sensors.get("temperature"),
        created_at=created_at
    )
    db.add(record_health)

    # ذخیره داده‌های سبک زندگی (LifestyleData)
    record_life = models.LifestyleData(
        user_id=user.id,
        steps=sensors.get("steps"),
        calories=None,
        sleep_hours=None,
        stress_level=None,
        created_at=created_at
    )
    db.add(record_life)

    db.commit()
    db.refresh(record_health)
    db.refresh(record_life)

    return APIResponse(
        ok=True,
        data={
            "health_id": record_health.id,
            "lifestyle_id": record_life.id,
            "timestamp": created_at.isoformat()
        }
    )
