"""I9 aggregate/baseline -> I7 derived pattern producer (consent-gated, linked-user only)."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i7.i9_patterns import upsert_i9_derived_pattern

def produce_i7_pattern_from_latest_rollup(
    db: Session,
    *,
    health_subject_id: int,
    measurement_type: str = "heart_rate",
    bucket_kind: str = "weekly",
    pattern_key: Optional[str] = None,
    commit: bool = True,
) -> dict[str, Any]:
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None:
        return {"status": "SUBJECT_NOT_FOUND"}
    if subject.linked_user_id is None:
        return {"status": "SKIPPED_NO_LINKED_ACCOUNT", "reason": "managed_subject_without_account"}
    user_id = subject.linked_user_id
    rollup = (
        db.query(models.PhysiologicalMeasurementRollup)
        .filter(
            models.PhysiologicalMeasurementRollup.health_subject_id == health_subject_id,
            models.PhysiologicalMeasurementRollup.measurement_type == measurement_type,
            models.PhysiologicalMeasurementRollup.bucket_kind == bucket_kind,
        )
        .order_by(models.PhysiologicalMeasurementRollup.bucket_start.desc())
        .first()
    )
    if rollup is None:
        return {"status": "NO_SOURCE_AGGREGATE"}
    key = pattern_key or f"i9:{measurement_type}:{bucket_kind}:latest"
    pattern = {
        "measurement_type": measurement_type,
        "bucket_kind": bucket_kind,
        "avg_value": rollup.avg_value,
        "sample_count": rollup.sample_count,
        "bucket_start": rollup.bucket_start.isoformat(),
        "source": "I9_AGGREGATE",
        "disclaimer": "DEVICE_REPORTED_AND_AGGREGATE_CONTEXT_NOT_DIAGNOSIS",
    }
    source_refs = [
        {
            "entity": "physiological_measurement_rollup",
            "id": int(rollup.id),
            "health_subject_id": health_subject_id,
        }
    ]
    prior_active = (
        db.query(models.UserI7DerivedPattern)
        .filter(
            models.UserI7DerivedPattern.user_id == user_id,
            models.UserI7DerivedPattern.pattern_key == key,
            models.UserI7DerivedPattern.status == "active",
        )
        .first()
    )
    prior_active_id = prior_active.id if prior_active is not None else None
    row = upsert_i9_derived_pattern(
        db,
        user_id=user_id,
        pattern_key=key,
        pattern=pattern,
        source_refs=source_refs,
        commit=commit,
    )
    if row is None:
        return {"status": "SKIPPED_NO_I6_WRITE_CONSENT"}
    if prior_active_id is not None and row.id == prior_active_id and row.status == "active":
        return {"status": "UNCHANGED", "pattern_id": row.id, "user_id": user_id}
    return {"status": "WRITTEN", "pattern_id": row.id, "user_id": user_id}
