"""Canonical device packet ingestion with client_packet_id idempotency."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.db03.physiological_idempotency import build_physiological_idempotency_key
from backend.app.services.i9.device_binding_service import DeviceBindingError, resolve_subject_for_device
from backend.app.services.i9.health_subject_service import resolve_linked_user_id_for_subject
from backend.app.services.vitals.vital_registry import VitalValidationError, validate_event

logger = logging.getLogger(__name__)

SUPPORTED_MEASUREMENT_TYPES = frozenset({"heart_rate", "blood_pressure", "glucose", "temperature", "spo2"})
CARDIAC_EVENT_OBSERVATION_TYPE = "device_reported_cardiac_event"


@dataclass
class PacketObservationIn:
    observation_type: str
    payload: Dict[str, Any]
    detected_at: Optional[datetime] = None


@dataclass
class DevicePacketIngestInput:
    client_packet_id: str
    measured_at: datetime
    sequence_number: Optional[int] = None
    measured_interval_start: Optional[datetime] = None
    measured_interval_end: Optional[datetime] = None
    gateway_received_at: Optional[datetime] = None
    transport: Optional[str] = None
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None
    algorithm_version: Optional[str] = None
    quality_metadata: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    observations: List[PacketObservationIn] = field(default_factory=list)


@dataclass
class DevicePacketIngestResult:
    packet: Optional[models.DevicePacket]
    dedupe_hit: bool
    health_subject_id: int
    binding_id: Optional[int]
    physiological_measurement_ids: List[int] = field(default_factory=list)
    cardiac_event_ids: List[int] = field(default_factory=list)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ingest_device_packet(
    db: Session,
    *,
    device: models.Device,
    packet_in: DevicePacketIngestInput,
    trace_id: str = "",
    commit: bool = True,
) -> DevicePacketIngestResult:
    """Ingest packet; idempotent on device_row_id + client_packet_id."""
    measured_at = _ensure_utc(packet_in.measured_at)
    server_received_at = datetime.now(timezone.utc)

    try:
        health_subject_id, binding = resolve_subject_for_device(db, device, measured_at=measured_at)
    except DeviceBindingError as exc:
        raise ValueError("NO_ACTIVE_DEVICE_SUBJECT_BINDING") from exc

    binding_id = binding.id if binding else device.current_binding_id

    existing = (
        db.query(models.DevicePacket)
        .filter(
            models.DevicePacket.device_row_id == device.id,
            models.DevicePacket.client_packet_id == packet_in.client_packet_id.strip(),
        )
        .first()
    )
    if existing is not None:
        return DevicePacketIngestResult(
            packet=existing,
            dedupe_hit=True,
            health_subject_id=existing.health_subject_id,
            binding_id=existing.binding_id,
        )

    packet = models.DevicePacket(
        device_row_id=device.id,
        device_logical_id=device.device_id,
        client_packet_id=packet_in.client_packet_id.strip(),
        sequence_number=packet_in.sequence_number,
        health_subject_id=health_subject_id,
        binding_id=binding_id,
        measured_at=measured_at,
        measured_interval_start=(
            _ensure_utc(packet_in.measured_interval_start) if packet_in.measured_interval_start else None
        ),
        measured_interval_end=(
            _ensure_utc(packet_in.measured_interval_end) if packet_in.measured_interval_end else None
        ),
        server_received_at=server_received_at,
        gateway_received_at=(
            _ensure_utc(packet_in.gateway_received_at) if packet_in.gateway_received_at else None
        ),
        transport=packet_in.transport,
        firmware_version=packet_in.firmware_version or device.firmware_version,
        hardware_version=packet_in.hardware_version or device.hardware_version,
        algorithm_version=packet_in.algorithm_version,
        quality_metadata_json=json.dumps(packet_in.quality_metadata) if packet_in.quality_metadata else None,
        provenance_json=json.dumps(packet_in.provenance) if packet_in.provenance else None,
        ingestion_status="accepted",
    )
    db.add(packet)
    db.flush()

    linked_user_id = resolve_linked_user_id_for_subject(db, health_subject_id)
    pm_ids: List[int] = []
    cardiac_ids: List[int] = []

    for obs in packet_in.observations:
        obs_type = obs.observation_type.strip().lower()
        obs_detected = _ensure_utc(obs.detected_at or measured_at)

        if obs_type == CARDIAC_EVENT_OBSERVATION_TYPE:
            event_code = str(obs.payload.get("event_code") or obs.payload.get("code") or "unknown")
            value_num = obs.payload.get("value")
            if value_num is not None:
                try:
                    value_num = float(value_num)
                except (TypeError, ValueError):
                    value_num = None
            cardiac = models.DeviceReportedCardiacEvent(
                device_packet_id=packet.id,
                health_subject_id=health_subject_id,
                event_code=event_code,
                event_value_numeric=value_num,
                event_value_json=json.dumps(obs.payload),
                detected_at=obs_detected,
                source_class="DEVICE_REPORTED",
                firmware_version=packet.firmware_version,
                hardware_version=packet.hardware_version,
                algorithm_version=packet.algorithm_version,
                provenance_json=json.dumps(
                    {
                        "source": "DEVICE",
                        "class": "DEVICE_REPORTED",
                        "device_id": device.device_id,
                        "client_packet_id": packet.client_packet_id,
                    }
                ),
            )
            db.add(cardiac)
            db.flush()
            cardiac_ids.append(int(cardiac.id))
            continue

        if obs_type not in SUPPORTED_MEASUREMENT_TYPES:
            raise VitalValidationError(f"Unsupported observation_type '{obs_type}'")

        event_type = obs_type if obs_type != "blood_pressure" else "blood_pressure"
        normalized = validate_event(event_type, obs.payload)
        pm_id = _write_physiological_measurement(
            db,
            device=device,
            health_subject_id=health_subject_id,
            linked_user_id=linked_user_id,
            measurement_type=obs_type,
            normalized=normalized,
            measured_at=obs_detected,
            received_at=server_received_at,
            client_packet_id=packet.client_packet_id,
            sequence_number=packet_in.sequence_number,
        )
        if pm_id is not None:
            pm_ids.append(pm_id)

    if commit:
        db.commit()
        db.refresh(packet)
    else:
        db.flush()

    logger.info(
        "[I9_PACKET] CREATED device=%s packet=%s subject=%s trace=%s",
        device.device_id,
        packet.client_packet_id,
        health_subject_id,
        trace_id,
    )
    return DevicePacketIngestResult(
        packet=packet,
        dedupe_hit=False,
        health_subject_id=health_subject_id,
        binding_id=binding_id,
        physiological_measurement_ids=pm_ids,
        cardiac_event_ids=cardiac_ids,
    )


def _write_physiological_measurement(
    db: Session,
    *,
    device: models.Device,
    health_subject_id: int,
    linked_user_id: Optional[int],
    measurement_type: str,
    normalized: Dict[str, Any],
    measured_at: datetime,
    received_at: datetime,
    client_packet_id: str,
    sequence_number: Optional[int],
) -> Optional[int]:
    if measurement_type == "heart_rate":
        numeric = normalized.get("bpm")
        unit = "bpm"
    elif measurement_type == "blood_pressure":
        numeric = float(normalized.get("sys", 0))
        unit = "mmHg"
    elif measurement_type == "glucose":
        numeric = normalized.get("glucose_mg_dl")
        unit = "mg/dL"
    elif measurement_type == "temperature":
        numeric = normalized.get("temperature_c")
        unit = "C"
    elif measurement_type == "spo2":
        numeric = normalized.get("spo2_percent") or normalized.get("percent")
        unit = "percent"
    else:
        return None

    if numeric is None:
        return None

    source_sequence = f"{client_packet_id}:{sequence_number}" if sequence_number is not None else client_packet_id
    idem = build_physiological_idempotency_key(
        device_id=device.id,
        measurement_type=measurement_type,
        measured_at=measured_at,
        source_sequence=source_sequence,
    )
    existing = db.query(models.PhysiologicalMeasurement).filter(models.PhysiologicalMeasurement.idempotency_key == idem).first()
    if existing:
        return int(existing.id)

    row = models.PhysiologicalMeasurement(
        user_id=linked_user_id,
        health_subject_id=health_subject_id,
        device_id=device.id,
        sensor_id=None,
        measurement_type=measurement_type,
        numeric_value=float(numeric),
        unit=unit,
        measured_at=measured_at,
        received_at=received_at,
        quality_state=normalized.get("quality") or "device_packet",
        idempotency_key=idem,
        source_sequence=source_sequence,
        ingestion_status="accepted",
    )
    db.add(row)
    db.flush()
    return int(row.id)
