"""Gate 5-B — Raw heart/ECG signal store-only ingestion."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.models import Device, DeviceSensor, RawSignalBatch
from backend.app.schemas.device import RawSignalBatchRequest
from backend.app.services.gate5.gadget_hub_status import is_gadget_hub

logger = logging.getLogger(__name__)

STORAGE_BACKEND_POSTGRES_JSON = "postgres_json"


class RawSignalIngestionError(Exception):
    """Base error for raw signal ingestion."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def build_raw_signal_dedupe_key(hub_device_row_id: int, sensor_key: str, client_batch_id: str) -> str:
    return f"raw_signal:{hub_device_row_id}:{sensor_key}:{client_batch_id}"


def _resolve_active_sensor(db: Session, hub: Device, sensor_key: str) -> Optional[DeviceSensor]:
    return (
        db.query(DeviceSensor)
        .filter(
            DeviceSensor.hub_device_id == hub.id,
            DeviceSensor.sensor_key == sensor_key,
            DeviceSensor.revoked_at.is_(None),
        )
        .first()
    )


def _enforce_signal_sensor_compatibility(signal_type: str, sensor: DeviceSensor) -> None:
    sensor_type = (sensor.sensor_type or "unknown").strip().lower()
    if signal_type == "ecg" and sensor_type != "ecg":
        raise RawSignalIngestionError(
            code="SIGNAL_SENSOR_MISMATCH",
            message="signal_type ecg requires sensor_type ecg",
            status_code=422,
        )
    if signal_type == "heart_rate_raw" and sensor_type not in {"ecg", "heart_rate"}:
        raise RawSignalIngestionError(
            code="SIGNAL_SENSOR_MISMATCH",
            message="signal_type heart_rate_raw requires sensor_type ecg or heart_rate",
            status_code=422,
        )


@dataclass
class RawSignalIngestionResult:
    batch_id: int
    dedupe_key: str
    received_at: datetime
    sample_count: int
    storage_backend: str
    dedupe_hit: bool
    message: Optional[str] = None


def ingest_raw_signal_batch(
    db: Session,
    *,
    hub: Device,
    body: RawSignalBatchRequest,
    now: Optional[datetime] = None,
) -> RawSignalIngestionResult:
    """
    Append-only raw signal batch ingest. No clinical interpretation or side effects
    beyond operational timestamps on hub/sensor rows.
    """
    if not is_gadget_hub(hub):
        raise RawSignalIngestionError(
            code="NOT_GADGET_HUB",
            message="Raw signal ingestion is only allowed for Gadget Hub devices",
            status_code=403,
        )

    sensor = _resolve_active_sensor(db, hub, body.sensor_key.strip())
    if sensor is None:
        raise RawSignalIngestionError(
            code="SENSOR_NOT_REGISTERED",
            message="Sensor not registered for this Gadget Hub",
            status_code=403,
        )

    _enforce_signal_sensor_compatibility(body.signal_type, sensor)

    now = now or datetime.utcnow()
    dedupe_key = build_raw_signal_dedupe_key(hub.id, sensor.sensor_key, body.client_batch_id.strip())

    existing = db.query(RawSignalBatch).filter(RawSignalBatch.dedupe_key == dedupe_key).first()
    if existing is not None:
        logger.info(
            "[RAW_SIGNAL] DUPLICATE hub=%s sensor=%s dedupe=%s batch_id=%s",
            hub.device_id,
            sensor.sensor_key,
            dedupe_key,
            existing.id,
        )
        return RawSignalIngestionResult(
            batch_id=existing.id,
            dedupe_key=existing.dedupe_key,
            received_at=existing.received_at,
            sample_count=existing.sample_count,
            storage_backend=existing.storage_backend,
            dedupe_hit=True,
            message="Batch already stored",
        )

    batch = RawSignalBatch(
        user_id=hub.user_id,
        hub_device_id=hub.id,
        hub_device_id_str=hub.device_id,
        sensor_id=sensor.id,
        sensor_key=sensor.sensor_key,
        signal_type=body.signal_type,
        sample_rate_hz=float(body.sample_rate_hz),
        started_at=body.started_at,
        ended_at=body.ended_at,
        sample_count=body.sample_count,
        samples_json=body.samples,
        metadata_json=body.metadata,
        quality_metadata_json=body.quality_metadata,
        client_batch_id=body.client_batch_id.strip(),
        dedupe_key=dedupe_key,
        received_at=now,
        created_at=now,
        storage_backend=STORAGE_BACKEND_POSTGRES_JSON,
        object_storage_key=None,
    )
    db.add(batch)

    sensor.last_signal_at = body.ended_at or now
    sensor.last_seen_at = now
    sensor.updated_at = now
    db.add(sensor)

    hub.last_seen_at = now
    db.add(hub)

    db.commit()
    db.refresh(batch)

    logger.info(
        "[RAW_SIGNAL] CREATED hub=%s sensor=%s batch_id=%s samples=%s signal_type=%s",
        hub.device_id,
        sensor.sensor_key,
        batch.id,
        batch.sample_count,
        batch.signal_type,
    )

    return RawSignalIngestionResult(
        batch_id=batch.id,
        dedupe_key=batch.dedupe_key,
        received_at=batch.received_at,
        sample_count=batch.sample_count,
        storage_backend=batch.storage_backend,
        dedupe_hit=False,
    )
