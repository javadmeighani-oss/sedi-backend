"""health_data → physiological_measurements backfill (§270.R)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.db03.physiological_idempotency import build_physiological_idempotency_key


@dataclass
class HealthBackfillCounts:
    source_rows_expected: int = 0
    mapped_rows: int = 0
    conflict_rows: int = 0
    unmapped_rows: int = 0
    skipped_no_hr: int = 0
    skipped_no_device: int = 0

    @property
    def unexplained_data_loss(self) -> int:
        # Rows without HR are intentionally skipped (not loss of HR authority).
        accountable_source = self.source_rows_expected - self.skipped_no_hr - self.skipped_no_device
        accounted = self.mapped_rows + self.conflict_rows + self.unmapped_rows
        return max(0, accountable_source - accounted)


def _parse_hr(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().lower().replace("bpm", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def backfill_health_data_to_physiological_measurements(db: Session) -> HealthBackfillCounts:
    counts = HealthBackfillCounts()
    rows = db.query(models.HealthData).order_by(models.HealthData.id).all()
    counts.source_rows_expected = len(rows)

    for row in rows:
        hr = _parse_hr(row.heart_rate)
        if hr is None:
            counts.skipped_no_hr += 1
            continue
        device = (
            db.query(models.Device)
            .filter(models.Device.user_id == row.user_id)
            .order_by(models.Device.id.asc())
            .first()
        )
        if device is None:
            # Retain legacy evidence; do not invent a device.
            counts.skipped_no_device += 1
            counts.unmapped_rows += 1
            continue

        created = row.created_at or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        idem = build_physiological_idempotency_key(
            device_id=device.id,
            measurement_type="heart_rate",
            measured_at=created,
            source_sequence=f"legacy_health_data:{row.id}",
        )
        existing = (
            db.query(models.PhysiologicalMeasurement)
            .filter(models.PhysiologicalMeasurement.idempotency_key == idem)
            .first()
        )
        if existing:
            counts.conflict_rows += 1
            continue
        try:
            db.add(
                models.PhysiologicalMeasurement(
                    user_id=row.user_id,
                    device_id=device.id,
                    sensor_id=None,
                    measurement_type="heart_rate",
                    numeric_value=hr,
                    unit="bpm",
                    measured_at=created,
                    received_at=created,
                    quality_state="legacy_import",
                    idempotency_key=idem,
                    source_sequence=f"legacy_health_data:{row.id}",
                    ingestion_status="legacy_import",
                )
            )
            counts.mapped_rows += 1
        except Exception:  # noqa: BLE001
            counts.unmapped_rows += 1

    db.flush()
    return counts
