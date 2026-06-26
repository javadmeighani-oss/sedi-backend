from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import get_db

router = APIRouter(prefix="/ops", tags=["Ops"])


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-ADMIN-TOKEN")) -> None:
    expected = os.environ.get("ADMIN_TOKEN") or ""
    if not expected:
        raise HTTPException(status_code=403, detail="admin_disabled")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="forbidden")


def _notifications_pending(db: Session) -> int:
    if hasattr(models.Notification, "status"):
        return db.query(models.Notification).filter(models.Notification.status == "pending").count()
    if hasattr(models.Notification, "is_sent"):
        return db.query(models.Notification).filter(models.Notification.is_sent.is_(False)).count()
    return 0


def _notifications_failed_24h(db: Session, since: datetime) -> int | None:
    if hasattr(models.Notification, "status") and hasattr(models.Notification, "created_at"):
        return (
            db.query(models.Notification)
            .filter(
                models.Notification.status == "failed",
                models.Notification.created_at >= since,
            )
            .count()
        )
    return None


def _device_events_24h(db: Session, since: datetime) -> int | None:
    event_model = getattr(models, "DeviceEvent", None)
    if event_model is None:
        return None
    if hasattr(event_model, "recorded_at"):
        return db.query(event_model).filter(event_model.recorded_at >= since).count()
    if hasattr(event_model, "created_at"):
        return db.query(event_model).filter(event_model.created_at >= since).count()
    return None


@router.get("/status")
def ops_status(
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    t0 = time.perf_counter()
    db.execute(text("select 1"))
    latency_ms = (time.perf_counter() - t0) * 1000

    now = datetime.utcnow()
    since = now - timedelta(hours=24)

    data = {
        "service": {
            "name": "sedi-backend",
            "now_utc": now.isoformat() + "Z",
        },
        "db": {
            "latency_ms": round(latency_ms, 3),
        },
        "counts": {
            "notifications_pending": _notifications_pending(db),
            "notifications_failed_24h": _notifications_failed_24h(db, since),
            "device_events_24h": _device_events_24h(db, since),
        },
        "runtime": {
            "DEVICE_AUTH_MODE": os.environ.get("DEVICE_AUTH_MODE"),
            "FCM_DISABLED": os.environ.get("FCM_DISABLED"),
            "APP_TIMEZONE": os.environ.get("APP_TIMEZONE"),
        },
    }
    return {"ok": True, "data": data, "error": None}


@router.get("/config/sms")
def ops_config_sms(_admin: None = Depends(require_admin)):
    """
    Admin-only: SMS config status (no secrets). Use to verify production env.
    Returns set/unset for each var; API keys are never exposed.
    """
    return {
        "ok": True,
        "data": {
            "SMS_DISABLED": "set" if os.environ.get("SMS_DISABLED") else "unset",
            "SMS_PROVIDER": "set" if os.environ.get("SMS_PROVIDER") else "unset",
            "MEDIANA_API_KEY": "set" if os.environ.get("MEDIANA_API_KEY") else "unset",
            "MEDIANA_OTP_PATTERN_CODE": "set"
            if os.environ.get("MEDIANA_OTP_PATTERN_CODE")
            else "unset",
        },
        "error": None,
    }
