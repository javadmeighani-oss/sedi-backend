"""Gate 5-E — Shadow ML inference record service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.models import (
    Device,
    MlInferenceRecord,
    MlModelRegistry,
    RawSignalBatch,
    RawSignalBatchFeature,
)
from backend.app.services.gate5.ml_safety import MlSafetyError, validate_inference_record_fields


class MlInferenceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class InferenceRecord:
    id: int
    user_id: int
    device_id: Optional[str]
    sensor_id: Optional[int]
    raw_signal_batch_id: Optional[int]
    raw_signal_batch_feature_id: Optional[int]
    model_id: int
    output_type: str
    score: Optional[float]
    confidence: Optional[float]
    features_summary_json: Optional[Dict[str, Any]]
    safety_status: str
    user_visible: bool
    created_at: datetime


def _serialize(row: MlInferenceRecord) -> InferenceRecord:
    return InferenceRecord(
        id=row.id,
        user_id=row.user_id,
        device_id=row.device_id,
        sensor_id=row.sensor_id,
        raw_signal_batch_id=row.raw_signal_batch_id,
        raw_signal_batch_feature_id=row.raw_signal_batch_feature_id,
        model_id=row.model_id,
        output_type=row.output_type,
        score=row.score,
        confidence=row.confidence,
        features_summary_json=row.features_summary_json if isinstance(row.features_summary_json, dict) else None,
        safety_status=row.safety_status,
        user_visible=bool(row.user_visible),
        created_at=row.created_at,
    )


def _validate_feature_link(
    db: Session,
    *,
    user_id: int,
    raw_signal_batch_id: Optional[int],
    raw_signal_batch_feature_id: Optional[int],
    device_id: Optional[str],
    sensor_id: Optional[int],
) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """Ensure linked batch/feature rows exist and belong to user_id."""
    resolved_device_id = device_id
    resolved_sensor_id = sensor_id
    resolved_batch_id = raw_signal_batch_id

    if raw_signal_batch_feature_id is not None:
        feature = (
            db.query(RawSignalBatchFeature)
            .filter(RawSignalBatchFeature.id == raw_signal_batch_feature_id)
            .first()
        )
        if not feature:
            raise MlInferenceError("FEATURE_NOT_FOUND", f"feature id {raw_signal_batch_feature_id} not found", 404)
        if feature.user_id != user_id:
            raise MlInferenceError("OWNERSHIP_MISMATCH", "feature does not belong to user", 403)
        if feature.processing_status != "completed":
            raise MlInferenceError("FEATURE_NOT_READY", "feature row is not completed", 422)
        resolved_batch_id = feature.raw_signal_batch_id
        resolved_sensor_id = feature.sensor_id
        hub = db.query(Device).filter(Device.id == feature.hub_device_id).first()
        if hub:
            resolved_device_id = hub.device_id

    if raw_signal_batch_id is not None and resolved_batch_id != raw_signal_batch_id:
        raise MlInferenceError("BATCH_MISMATCH", "raw_signal_batch_id does not match feature row", 422)

    if raw_signal_batch_id is not None and raw_signal_batch_feature_id is None:
        batch = db.query(RawSignalBatch).filter(RawSignalBatch.id == raw_signal_batch_id).first()
        if not batch:
            raise MlInferenceError("BATCH_NOT_FOUND", f"batch id {raw_signal_batch_id} not found", 404)
        if batch.user_id != user_id:
            raise MlInferenceError("OWNERSHIP_MISMATCH", "batch does not belong to user", 403)
        resolved_device_id = resolved_device_id or batch.hub_device_id_str
        resolved_sensor_id = resolved_sensor_id or batch.sensor_id

    return resolved_device_id, resolved_sensor_id, resolved_batch_id


def create_inference_record(
    db: Session,
    *,
    user_id: int,
    model_id: int,
    output_type: str,
    device_id: Optional[str] = None,
    sensor_id: Optional[int] = None,
    raw_signal_batch_id: Optional[int] = None,
    raw_signal_batch_feature_id: Optional[int] = None,
    score: Optional[float] = None,
    confidence: Optional[float] = None,
    features_summary_json: Optional[Dict[str, Any]] = None,
    raw_output_json: Optional[Dict[str, Any]] = None,
    safety_status: str = "shadow_only",
    user_visible: bool = False,
) -> InferenceRecord:
    model = db.query(MlModelRegistry).filter(MlModelRegistry.id == model_id).first()
    if not model:
        raise MlInferenceError("MODEL_NOT_FOUND", f"model id {model_id} not found", 404)

    try:
        normalized_type = validate_inference_record_fields(
            output_type=output_type,
            raw_output_json=raw_output_json,
            features_summary_json=features_summary_json,
            user_visible=user_visible,
        )
    except MlSafetyError as exc:
        raise MlInferenceError("SAFETY_VIOLATION", str(exc), 422) from exc

    if user_visible:
        raise MlInferenceError("USER_VISIBLE_FORBIDDEN", "user_visible must be false", 422)

    resolved_device_id, resolved_sensor_id, resolved_batch_id = _validate_feature_link(
        db,
        user_id=user_id,
        raw_signal_batch_id=raw_signal_batch_id,
        raw_signal_batch_feature_id=raw_signal_batch_feature_id,
        device_id=device_id,
        sensor_id=sensor_id,
    )

    row = MlInferenceRecord(
        user_id=user_id,
        device_id=resolved_device_id,
        sensor_id=resolved_sensor_id,
        raw_signal_batch_id=resolved_batch_id,
        raw_signal_batch_feature_id=raw_signal_batch_feature_id,
        model_id=model_id,
        output_type=normalized_type,
        score=score,
        confidence=confidence,
        features_summary_json=features_summary_json,
        raw_output_json=raw_output_json,
        safety_status=safety_status,
        user_visible=False,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


def list_inference_records(db: Session, *, limit: int = 50) -> List[InferenceRecord]:
    rows = (
        db.query(MlInferenceRecord)
        .order_by(MlInferenceRecord.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [_serialize(r) for r in rows]


def get_inference_record(db: Session, record_id: int) -> InferenceRecord:
    row = db.query(MlInferenceRecord).filter(MlInferenceRecord.id == record_id).first()
    if not row:
        raise MlInferenceError("RECORD_NOT_FOUND", f"inference record {record_id} not found", 404)
    return _serialize(row)


def inference_record_to_api_dict(record: InferenceRecord) -> Dict[str, Any]:
    """API-safe dict — excludes raw_output_json."""
    return {
        "id": record.id,
        "user_id": record.user_id,
        "device_id": record.device_id,
        "sensor_id": record.sensor_id,
        "raw_signal_batch_id": record.raw_signal_batch_id,
        "raw_signal_batch_feature_id": record.raw_signal_batch_feature_id,
        "model_id": record.model_id,
        "output_type": record.output_type,
        "score": record.score,
        "confidence": record.confidence,
        "features_summary_json": record.features_summary_json,
        "safety_status": record.safety_status,
        "user_visible": record.user_visible,
        "created_at": record.created_at.isoformat() + "Z" if record.created_at else None,
    }
