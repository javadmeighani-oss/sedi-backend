from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import get_db
from backend.app.schemas.raw_signal_ops import (
    RawSignalProcessBatchData,
    RawSignalProcessBatchRequest,
    RawSignalProcessBatchResponse,
    RawSignalProcessPendingData,
    RawSignalProcessPendingRequest,
    RawSignalProcessPendingResponse,
)
from backend.app.services.gate5.raw_signal_feature_extraction import (
    RawSignalFeatureExtractionError,
    process_pending_raw_signal_batches,
    process_raw_signal_batch,
)

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


@router.post("/raw-signals/process-pending", response_model=RawSignalProcessPendingResponse)
def ops_process_pending_raw_signals(
    body: RawSignalProcessPendingRequest,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin-only: process pending raw signal batches (technical features only).
    Does not expose raw samples or create notifications.
    """
    summary = process_pending_raw_signal_batches(
        db,
        limit=body.limit,
        processing_version=body.processing_version,
    )
    return RawSignalProcessPendingResponse(
        ok=True,
        data=RawSignalProcessPendingData(
            processed=summary.processed,
            completed=summary.completed,
            failed=summary.failed,
            skipped=summary.skipped,
            processing_version=summary.processing_version,
        ),
    )


@router.post("/raw-signals/process/{batch_id}", response_model=RawSignalProcessBatchResponse)
def ops_process_raw_signal_batch(
    batch_id: int,
    body: RawSignalProcessBatchRequest,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin-only: extract technical features for one raw signal batch.
    Does not expose raw samples or create clinical side effects.
    """
    try:
        result = process_raw_signal_batch(
            db,
            batch_id,
            processing_version=body.processing_version,
        )
    except RawSignalFeatureExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return RawSignalProcessBatchResponse(
        ok=True,
        data=RawSignalProcessBatchData(
            batch_id=result.batch_id,
            feature_id=result.feature_id,
            processing_status=result.processing_status,
            processing_version=result.processing_version,
        ),
    )
