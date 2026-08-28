"""Canonical I9 longitudinal read surface (subject-attributed, fail-closed)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.aggregation_service import compute_aggregate_for_range
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    preferred_language_for_subject,
    require_account_subject_access,
)

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class LongitudinalReadError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _parse_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def list_observations(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
    measurement_type: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> List[dict]:
    subject = require_account_subject_access(db, account_user_id, health_subject_id)
    limit = min(max(1, limit), MAX_LIMIT)
    offset = max(0, offset)
    q = db.query(models.PhysiologicalMeasurement).filter(
        models.PhysiologicalMeasurement.health_subject_id == subject.id,
    )
    if measurement_type:
        q = q.filter(models.PhysiologicalMeasurement.measurement_type == measurement_type)
    start_utc = _parse_dt(start)
    end_utc = _parse_dt(end)
    if start_utc:
        q = q.filter(models.PhysiologicalMeasurement.measured_at >= start_utc)
    if end_utc:
        q = q.filter(models.PhysiologicalMeasurement.measured_at < end_utc)
    rows = (
        q.order_by(models.PhysiologicalMeasurement.measured_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    out: List[dict] = []
    for row in rows:
        device = db.query(models.Device).filter(models.Device.id == row.device_id).first()
        out.append(
            {
                "id": row.id,
                "measurement_type": row.measurement_type,
                "numeric_value": row.numeric_value,
                "unit": row.unit,
                "measured_at": row.measured_at,
                "received_at": row.received_at,
                "quality_state": row.quality_state,
                "provenance": {
                    "device_id": row.device_id,
                    "device_identifier": device.device_id if device else None,
                    "source_sequence": row.source_sequence,
                },
            }
        )
    return out


def list_aggregates(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
    measurement_type: str,
    bucket_kind: str,
    start: datetime,
    end: datetime,
) -> List[dict]:
    subject = require_account_subject_access(db, account_user_id, health_subject_id)
    lang = preferred_language_for_subject(db, subject)
    return compute_aggregate_for_range(
        db,
        health_subject_id=subject.id,
        measurement_type=measurement_type,
        bucket_kind=bucket_kind,  # type: ignore[arg-type]
        range_start=_parse_dt(start) or datetime.min.replace(tzinfo=timezone.utc),
        range_end=_parse_dt(end) or datetime.now(timezone.utc),
        preferred_language=lang,
    )


def list_cardiac_events(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> List[dict]:
    subject = require_account_subject_access(db, account_user_id, health_subject_id)
    limit = min(max(1, limit), MAX_LIMIT)
    offset = max(0, offset)
    q = db.query(models.DeviceReportedCardiacEvent).filter(
        models.DeviceReportedCardiacEvent.health_subject_id == subject.id,
    )
    start_utc = _parse_dt(start)
    end_utc = _parse_dt(end)
    if start_utc:
        q = q.filter(models.DeviceReportedCardiacEvent.detected_at >= start_utc)
    if end_utc:
        q = q.filter(models.DeviceReportedCardiacEvent.detected_at < end_utc)
    rows = (
        q.order_by(models.DeviceReportedCardiacEvent.detected_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "event_code": row.event_code,
            "event_value_numeric": row.event_value_numeric,
            "detected_at": row.detected_at,
            "source_class": row.source_class,
            "firmware_version": row.firmware_version,
            "hardware_version": row.hardware_version,
            "algorithm_version": row.algorithm_version,
            "device_packet_id": row.device_packet_id,
            "provenance_json": row.provenance_json,
        }
        for row in rows
    ]


def list_baselines(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
    measurement_type: Optional[str] = None,
) -> dict:
    subject = require_account_subject_access(db, account_user_id, health_subject_id)
    q = db.query(models.PhysiologicalBaseline).filter(
        models.PhysiologicalBaseline.health_subject_id == subject.id,
    )
    if measurement_type:
        q = q.filter(models.PhysiologicalBaseline.measurement_type == measurement_type)
    rows = q.order_by(models.PhysiologicalBaseline.derived_at.desc()).limit(20).all()
    return {
        "baseline_computation": "NEEDS_PRODUCT_DECISION",
        "stored_baselines": [
            {
                "id": r.id,
                "measurement_type": r.measurement_type,
                "baseline_value": r.baseline_value,
                "window_start": r.window_start,
                "window_end": r.window_end,
                "derived_at": r.derived_at,
                "coverage": r.coverage,
                "quality": r.quality,
            }
            for r in rows
        ],
    }
