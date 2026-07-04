"""Gate 5-E — ML model registry service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.models import MlModelRegistry
from backend.app.services.gate5.ml_safety import (
    ALLOWED_INPUT_TYPES,
    ALLOWED_SIGNAL_FAMILIES,
    MlSafetyError,
    validate_json_payload,
    validate_model_status,
)


class MlRegistryError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class ModelRecord:
    id: int
    model_name: str
    model_version: str
    signal_family: str
    input_type: str
    status: str
    training_dataset: Optional[str]
    metrics_json: Optional[Dict[str, Any]]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


def _serialize(row: MlModelRegistry) -> ModelRecord:
    return ModelRecord(
        id=row.id,
        model_name=row.model_name,
        model_version=row.model_version,
        signal_family=row.signal_family,
        input_type=row.input_type,
        status=row.status,
        training_dataset=row.training_dataset,
        metrics_json=row.metrics_json if isinstance(row.metrics_json, dict) else None,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def create_model(
    db: Session,
    *,
    model_name: str,
    model_version: str,
    signal_family: str,
    input_type: str,
    status: str = "research",
    training_dataset: Optional[str] = None,
    metrics_json: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> ModelRecord:
    name = (model_name or "").strip()
    version = (model_version or "").strip()
    if not name or not version:
        raise MlRegistryError("INVALID_MODEL", "model_name and model_version are required")

    family = (signal_family or "").strip().lower()
    if family not in ALLOWED_SIGNAL_FAMILIES:
        raise MlRegistryError(
            "INVALID_SIGNAL_FAMILY",
            f"signal_family must be one of: {', '.join(sorted(ALLOWED_SIGNAL_FAMILIES))}",
        )

    inp = (input_type or "").strip().lower()
    if inp not in ALLOWED_INPUT_TYPES:
        raise MlRegistryError(
            "INVALID_INPUT_TYPE",
            f"input_type must be one of: {', '.join(sorted(ALLOWED_INPUT_TYPES))}",
        )

    try:
        validated_status = validate_model_status(status)
    except MlSafetyError as exc:
        raise MlRegistryError("INVALID_STATUS", str(exc)) from exc

    if validated_status == "active":
        raise MlRegistryError(
            "ACTIVE_NOT_ALLOWED",
            "models cannot be set to active via API in Gate 5-E/F/G",
            status_code=422,
        )

    try:
        validate_json_payload(metrics_json, context="metrics_json")
    except MlSafetyError as exc:
        raise MlRegistryError("INVALID_METRICS", str(exc)) from exc

    existing = (
        db.query(MlModelRegistry)
        .filter(MlModelRegistry.model_name == name, MlModelRegistry.model_version == version)
        .first()
    )
    if existing:
        raise MlRegistryError(
            "DUPLICATE_MODEL_VERSION",
            f"model {name} version {version} already exists",
            status_code=409,
        )

    now = datetime.utcnow()
    row = MlModelRegistry(
        model_name=name,
        model_version=version,
        signal_family=family,
        input_type=inp,
        status=validated_status,
        training_dataset=(training_dataset or None),
        metrics_json=metrics_json,
        notes=notes,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


def list_models(db: Session, *, limit: int = 50) -> List[ModelRecord]:
    rows = db.query(MlModelRegistry).order_by(MlModelRegistry.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_serialize(r) for r in rows]


def get_model(db: Session, model_id: int) -> ModelRecord:
    row = db.query(MlModelRegistry).filter(MlModelRegistry.id == model_id).first()
    if not row:
        raise MlRegistryError("MODEL_NOT_FOUND", f"model id {model_id} not found", status_code=404)
    return _serialize(row)


def get_or_create_baseline_model(db: Session) -> MlModelRegistry:
    """Return the default baseline anomaly model row (research status)."""
    row = (
        db.query(MlModelRegistry)
        .filter(
            MlModelRegistry.model_name == "gate5_baseline_anomaly",
            MlModelRegistry.model_version == "v1",
        )
        .first()
    )
    if row:
        return row

    now = datetime.utcnow()
    row = MlModelRegistry(
        model_name="gate5_baseline_anomaly",
        model_version="v1",
        signal_family="ecg",
        input_type="raw_signal_features",
        status="research",
        training_dataset="internal_baseline_rules",
        metrics_json={"kind": "rule_based_baseline", "version": "gate5f_v1"},
        notes="Non-clinical baseline anomaly engine for Gate 5-F",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
