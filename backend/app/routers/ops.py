from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import get_db
from backend.app.schemas.raw_signal_ops import (
    DEFAULT_PROCESSING_VERSION,
    RawSignalBatchStatusData,
    RawSignalBatchStatusResponse,
    RawSignalProcessBatchData,
    RawSignalProcessBatchRequest,
    RawSignalProcessBatchResponse,
    RawSignalProcessPendingData,
    RawSignalProcessPendingRequest,
    RawSignalProcessPendingResponse,
)
from backend.app.services.gate5.raw_signal_feature_extraction import (
    RawSignalFeatureExtractionError,
    get_raw_signal_batch_processing_status,
    process_pending_raw_signal_batches,
    process_raw_signal_batch,
)
from backend.app.schemas.ml_ops import (
    MlBaselineRunData,
    MlBaselineRunResponse,
    MlCareBridgeData,
    MlCareBridgeResponse,
    MlInferenceCreateRequest,
    MlInferenceData,
    MlInferenceListData,
    MlInferenceListResponse,
    MlInferenceResponse,
    MlModelCreateRequest,
    MlModelData,
    MlModelListData,
    MlModelListResponse,
    MlModelResponse,
)
from backend.app.services.gate5.ml_baseline_anomaly import BaselineAnomalyError, run_baseline_anomaly
from backend.app.services.gate5.ml_care_bridge import MlCareBridgeError, run_care_bridge
from backend.app.services.gate5.ml_flags import (
    ml_flags_snapshot,
    ml_processing_enabled,
    ml_shadow_enabled,
)
from backend.app.services.gate5.ml_registry import MlRegistryError, create_model, get_model, list_models
from backend.app.services.gate5.ml_shadow_inference import (
    MlInferenceError,
    create_inference_record,
    get_inference_record,
    list_inference_records,
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


def _raise_extraction_error(exc: RawSignalFeatureExtractionError) -> None:
    if exc.code == "LIMIT_EXCEEDS_MAX":
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


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
            "GATE5_ML_FLAGS": ml_flags_snapshot(),
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
    try:
        summary = process_pending_raw_signal_batches(
            db,
            limit=body.limit,
            processing_version=body.processing_version,
            dry_run=body.dry_run,
            source="manual_ops",
        )
    except RawSignalFeatureExtractionError as exc:
        _raise_extraction_error(exc)

    return RawSignalProcessPendingResponse(
        ok=True,
        data=RawSignalProcessPendingData(
            processed=summary.processed,
            completed=summary.completed,
            failed=summary.failed,
            skipped=summary.skipped,
            processing_version=summary.processing_version,
            effective_limit=summary.effective_limit,
            dry_run=summary.dry_run,
            duration_ms=summary.duration_ms,
            candidate_batch_ids=summary.candidate_batch_ids,
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
            allow_retry=body.allow_retry,
            source="manual_ops",
        )
    except RawSignalFeatureExtractionError as exc:
        _raise_extraction_error(exc)

    return RawSignalProcessBatchResponse(
        ok=True,
        data=RawSignalProcessBatchData(
            batch_id=result.batch_id,
            feature_id=result.feature_id,
            processing_status=result.processing_status,
            processing_version=result.processing_version,
            skipped=result.skipped,
        ),
    )


@router.get("/raw-signals/status/{batch_id}", response_model=RawSignalBatchStatusResponse)
def ops_raw_signal_batch_status(
    batch_id: int,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
    processing_version: str = Query(default=DEFAULT_PROCESSING_VERSION, max_length=32),
):
    """
    Admin-only: processing metadata for one raw signal batch (no samples or feature payloads).
    """
    status = get_raw_signal_batch_processing_status(
        db,
        batch_id,
        processing_version=processing_version,
    )
    return RawSignalBatchStatusResponse(
        ok=True,
        data=RawSignalBatchStatusData(
            batch_id=status.batch_id,
            has_batch=status.has_batch,
            processing_version=status.processing_version,
            feature_id=status.feature_id,
            processing_status=status.processing_status,
            error_code=status.error_code,
            processed_at=status.processed_at,
            created_at=status.created_at,
        ),
    )


def _model_to_data(record) -> MlModelData:
    return MlModelData(
        id=record.id,
        model_name=record.model_name,
        model_version=record.model_version,
        signal_family=record.signal_family,
        input_type=record.input_type,
        status=record.status,
        training_dataset=record.training_dataset,
        metrics_json=record.metrics_json,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _inference_to_data(record) -> MlInferenceData:
    return MlInferenceData(
        id=record.id,
        user_id=record.user_id,
        device_id=record.device_id,
        sensor_id=record.sensor_id,
        raw_signal_batch_id=record.raw_signal_batch_id,
        raw_signal_batch_feature_id=record.raw_signal_batch_feature_id,
        model_id=record.model_id,
        output_type=record.output_type,
        score=record.score,
        confidence=record.confidence,
        features_summary_json=record.features_summary_json,
        safety_status=record.safety_status,
        user_visible=record.user_visible,
        created_at=record.created_at,
    )


@router.post("/ml/models", response_model=MlModelResponse, status_code=201)
def ops_create_ml_model(
    body: MlModelCreateRequest,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: register an internal ML model (research/shadow)."""
    try:
        record = create_model(
            db,
            model_name=body.model_name,
            model_version=body.model_version,
            signal_family=body.signal_family,
            input_type=body.input_type,
            status=body.status,
            training_dataset=body.training_dataset,
            metrics_json=body.metrics_json,
            notes=body.notes,
        )
    except MlRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return MlModelResponse(ok=True, data=_model_to_data(record))


@router.get("/ml/models", response_model=MlModelListResponse)
def ops_list_ml_models(
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Admin-only: list ML models."""
    records = list_models(db, limit=limit)
    return MlModelListResponse(
        ok=True,
        data=MlModelListData(models=[_model_to_data(r) for r in records], count=len(records)),
    )


@router.get("/ml/models/{model_id}", response_model=MlModelResponse)
def ops_get_ml_model(
    model_id: int,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: get one ML model."""
    try:
        record = get_model(db, model_id)
    except MlRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return MlModelResponse(ok=True, data=_model_to_data(record))


@router.post("/ml/inference-records", response_model=MlInferenceResponse, status_code=201)
def ops_create_inference_record(
    body: MlInferenceCreateRequest,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: store shadow inference record (requires SEDI_GATE5_ML_SHADOW_ENABLED)."""
    if not ml_shadow_enabled():
        raise HTTPException(status_code=403, detail="ml_shadow_disabled")
    try:
        record = create_inference_record(
            db,
            user_id=body.user_id,
            model_id=body.model_id,
            output_type=body.output_type,
            device_id=body.device_id,
            sensor_id=body.sensor_id,
            raw_signal_batch_id=body.raw_signal_batch_id,
            raw_signal_batch_feature_id=body.raw_signal_batch_feature_id,
            score=body.score,
            confidence=body.confidence,
            features_summary_json=body.features_summary_json,
            raw_output_json=body.raw_output_json,
            safety_status=body.safety_status,
            user_visible=body.user_visible,
        )
    except MlInferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return MlInferenceResponse(ok=True, data=_inference_to_data(record))


@router.get("/ml/inference-records", response_model=MlInferenceListResponse)
def ops_list_inference_records(
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Admin-only: list shadow inference records (no raw_output_json)."""
    records = list_inference_records(db, limit=limit)
    return MlInferenceListResponse(
        ok=True,
        data=MlInferenceListData(
            records=[_inference_to_data(r) for r in records],
            count=len(records),
        ),
    )


@router.get("/ml/inference-records/{record_id}", response_model=MlInferenceResponse)
def ops_get_inference_record(
    record_id: int,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: get one inference record (no raw_output_json)."""
    try:
        record = get_inference_record(db, record_id)
    except MlInferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return MlInferenceResponse(ok=True, data=_inference_to_data(record))


@router.post("/ml/run-baseline/{feature_id}", response_model=MlBaselineRunResponse)
def ops_run_baseline_anomaly(
    feature_id: int,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: run baseline anomaly on a feature row (requires SEDI_GATE5_ML_PROCESSING_ENABLED)."""
    if not ml_processing_enabled():
        raise HTTPException(status_code=403, detail="ml_processing_disabled")
    try:
        result = run_baseline_anomaly(db, feature_id, persist=True)
    except BaselineAnomalyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return MlBaselineRunResponse(
        ok=True,
        data=MlBaselineRunData(
            feature_id=feature_id,
            inference_record_id=result.inference_record.id,
            output_type=result.output_type,
            score=result.score,
            confidence=result.confidence,
            features_summary=result.features_summary,
        ),
    )


@router.post("/ml/inference-records/{record_id}/care-bridge/dry-run", response_model=MlCareBridgeResponse)
def ops_care_bridge_dry_run(
    record_id: int,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: preview V1 care suggestion text without side effects."""
    try:
        result = run_care_bridge(db, record_id, dry_run=True)
    except MlCareBridgeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return MlCareBridgeResponse(ok=True, data=_care_bridge_to_data(result))


@router.post("/ml/inference-records/{record_id}/care-bridge", response_model=MlCareBridgeResponse)
def ops_care_bridge(
    record_id: int,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: ML care bridge (default OFF — requires SEDI_GATE5_ML_CARE_BRIDGE_ENABLED)."""
    try:
        result = run_care_bridge(db, record_id, dry_run=False)
    except MlCareBridgeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return MlCareBridgeResponse(ok=True, data=_care_bridge_to_data(result))


def _care_bridge_to_data(result) -> MlCareBridgeData:
    return MlCareBridgeData(
        record_id=result.record_id,
        output_type=result.output_type,
        care_suggestion_text=result.care_suggestion_text,
        dry_run=result.dry_run,
        bridge_enabled=result.bridge_enabled,
        notification_enabled=result.notification_enabled,
        chat_context_enabled=result.chat_context_enabled,
        device_event_id=result.device_event_id,
        notification_id=result.notification_id,
        interaction_event_id=result.interaction_event_id,
        blocked_reason=result.blocked_reason,
    )
