"""I9 DeviceReportedVitalStatus — gadget STABLE|UNSTABLE authority only.

Backend must not recompute status from HR/MAD/baseline/thresholds/RAG/LLM.
STABLE != medically safe. UNSTABLE != danger/emergency/diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models

STATUS_STABLE = "STABLE"
STATUS_UNSTABLE = "UNSTABLE"
ALLOWED_STATUSES = frozenset({STATUS_STABLE, STATUS_UNSTABLE})
SOURCE_CLASS = "DEVICE_REPORTED"
OBSERVATION_TYPE = "device_reported_vital_status"


@dataclass(frozen=True)
class EffectiveVitalStatus:
    status: str
    row_id: int
    detected_at: datetime
    health_subject_id: int
    device_packet_id: int


def normalize_device_reported_status(raw: object) -> str:
    if raw is None:
        raise ValueError("DEVICE_REPORTED_VITAL_STATUS_MISSING")
    text = str(raw).strip().upper()
    if text not in ALLOWED_STATUSES:
        raise ValueError("DEVICE_REPORTED_VITAL_STATUS_INVALID")
    return text


def get_effective_device_reported_vital_status(
    db: Session,
    *,
    health_subject_id: int,
    exclude_id: Optional[int] = None,
) -> Optional[EffectiveVitalStatus]:
    """Latest eligible status by device detected_at (then id), not insert order."""
    q = db.query(models.DeviceReportedVitalStatus).filter(
        models.DeviceReportedVitalStatus.health_subject_id == int(health_subject_id),
        models.DeviceReportedVitalStatus.source_class == SOURCE_CLASS,
    )
    if exclude_id is not None:
        q = q.filter(models.DeviceReportedVitalStatus.id != int(exclude_id))
    row = (
        q.order_by(
            models.DeviceReportedVitalStatus.detected_at.desc(),
            models.DeviceReportedVitalStatus.id.desc(),
        )
        .first()
    )
    if row is None:
        return None
    return EffectiveVitalStatus(
        status=str(row.status),
        row_id=int(row.id),
        detected_at=row.detected_at
        if row.detected_at.tzinfo
        else row.detected_at.replace(tzinfo=timezone.utc),
        health_subject_id=int(row.health_subject_id),
        device_packet_id=int(row.device_packet_id),
    )
