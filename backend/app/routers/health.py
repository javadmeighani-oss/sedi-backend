# app/routers/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Any, Optional

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.health import HealthDataAddRequest, HealthDataResponse
from backend.app.core.ai_text_engine import generate_notification_text, NOTIF_TYPE_HEALTH_CHECK
from backend.app.services.notification_engine import DecisionEngine
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()


def _parse_vital(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _serialize_health(record: models.HealthData) -> dict:
    return HealthDataResponse(
        id=record.id,
        user_id=record.user_id,
        heart_rate=_parse_vital(record.heart_rate),
        temperature=_parse_vital(record.temperature),
        spo2=_parse_vital(record.spo2),
        created_at=record.created_at,
    ).model_dump()


def _build_health_summary(data: models.HealthData) -> str:
    parts = []
    if data.heart_rate is not None:
        parts.append(f"heart_rate={data.heart_rate}")
    if data.temperature is not None:
        parts.append(f"temperature={data.temperature}")
    if data.spo2 is not None:
        parts.append(f"spo2={data.spo2}")
    return ", ".join(parts) if parts else "No vitals provided."

def _store_vital(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return str(value)


@router.post("/add", response_model=APIResponse)
def add_health_data(
    body: HealthDataAddRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add health vitals for the authenticated user and generate a smart notification.

    Requires Bearer JWT. user_id is derived from the token only.
    """
    user = auth_user

    data = models.HealthData(
        user_id=user.id,
        heart_rate=_store_vital(body.heart_rate),
        temperature=_store_vital(body.temperature),
        spo2=_store_vital(body.spo2),
        created_at=datetime.utcnow(),
    )
    db.add(data)
    db.commit()
    db.refresh(data)

    msg = generate_notification_text(
        language=user.preferred_language or "en",
        notification_type=NOTIF_TYPE_HEALTH_CHECK,
        user_name=user.name or "User",
        health_summary=_build_health_summary(data),
    )

    decision_engine = DecisionEngine(db)
    notif = decision_engine.evaluate_health_data(user.id, data)

    if not notif:
        notif = decision_engine.create_health_alert(
            user_id=user.id,
            alert_code="health_data_update",
            alert_reason=msg,
            priority="normal",
        )

    print(f"[HEALTH] New health data saved for user_id={user.id}")
    print(f"[NOTIF] {msg}")

    return APIResponse(
        ok=True,
        data={
            "user_id": user.id,
            "health_id": data.id,
            "notification_id": notif.id,
            "message": msg,
        },
    )


@router.get("/latest", response_model=APIResponse)
def get_latest_health_data(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the latest HealthData row for the authenticated user."""
    latest = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == auth_user.id)
        .order_by(models.HealthData.created_at.desc(), models.HealthData.id.desc())
        .first()
    )
    return APIResponse(ok=True, data=_serialize_health(latest) if latest else None)


@router.get("/context", response_model=APIResponse)
def get_health_context(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return health context for the authenticated user (latest record + counts)."""
    user_id = auth_user.id
    latest = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == user_id)
        .order_by(models.HealthData.created_at.desc(), models.HealthData.id.desc())
        .first()
    )
    total_records = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == user_id)
        .count()
    )

    last_update_minutes_ago: Optional[int] = None
    if latest and latest.created_at:
        delta = datetime.utcnow() - latest.created_at
        last_update_minutes_ago = max(0, int(delta.total_seconds() // 60))

    return APIResponse(
        ok=True,
        data={
            "latest": _serialize_health(latest) if latest else None,
            "total_records": total_records,
            "last_update_minutes_ago": last_update_minutes_ago,
        },
    )
