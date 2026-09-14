"""I9 vital observation context persistence/load (G13).

Persists ONLY explicitly supplied authoritative context into
i9_vital_observation_contexts. Idempotent. No clinical interpretation.
No confirmation algorithm. Does not invent activity/altitude/temp method.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.vital_observation_context import (
    AuthorityState,
    ContextualField,
    VitalObservationContext,
    _known,
    _unknown,
)

logger = logging.getLogger(__name__)

SOURCE_PHYSIOLOGICAL_MEASUREMENT = "PHYSIOLOGICAL_MEASUREMENT"
SOURCE_LEGACY_HEALTHDATA = "LEGACY_HEALTHDATA"


class ContextPersistenceError(ValueError):
    """Fail-closed persistence/load error."""


@dataclass(frozen=True)
class ContextPersistInput:
    health_subject_id: int
    source_class: str
    source_row_id: int
    metric: str
    observed_at: datetime
    physiological_measurement_id: Optional[int] = None
    health_data_id: Optional[int] = None
    activity_state: Optional[str] = None
    altitude_value: Optional[float] = None
    altitude_unit: Optional[str] = None
    temperature_method: Optional[str] = None
    quality_state: Optional[str] = None
    confirmation_state: Optional[str] = None
    context_authority: Optional[dict[str, Any]] = None


def build_occurrence_key(*, source_class: str, source_row_id: int, metric: str) -> str:
    return f"i9:voc:{source_class}:{int(source_row_id)}:{metric}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _has_any_authoritative_value(inp: ContextPersistInput) -> bool:
    return any(
        v not in (None, "")
        for v in (
            inp.activity_state,
            inp.altitude_value,
            inp.temperature_method,
            inp.quality_state,
            inp.confirmation_state,
        )
    )


def persist_vital_observation_context(
    db: Session,
    inp: ContextPersistInput,
    *,
    commit: bool = False,
) -> Optional[models.I9VitalObservationContext]:
    """Idempotent upsert of authoritative context. Returns None if nothing useful to store."""
    if inp.health_subject_id is None:
        raise ContextPersistenceError("SUBJECT_REQUIRED")
    if inp.source_class not in (SOURCE_PHYSIOLOGICAL_MEASUREMENT, SOURCE_LEGACY_HEALTHDATA):
        raise ContextPersistenceError("SOURCE_CLASS_INVALID")
    if not inp.metric:
        raise ContextPersistenceError("METRIC_REQUIRED")

    subject = (
        db.query(models.HealthSubject)
        .filter(models.HealthSubject.id == int(inp.health_subject_id))
        .first()
    )
    if subject is None:
        raise ContextPersistenceError("SUBJECT_NOT_FOUND")

    if inp.physiological_measurement_id is not None:
        pm = (
            db.query(models.PhysiologicalMeasurement)
            .filter(models.PhysiologicalMeasurement.id == int(inp.physiological_measurement_id))
            .first()
        )
        if pm is None:
            raise ContextPersistenceError("PM_NOT_FOUND")
        if pm.health_subject_id is not None and int(pm.health_subject_id) != int(inp.health_subject_id):
            raise ContextPersistenceError("SUBJECT_MISMATCH")
        if int(inp.source_row_id) != int(pm.id):
            raise ContextPersistenceError("SOURCE_ROW_MISMATCH")
        if inp.source_class != SOURCE_PHYSIOLOGICAL_MEASUREMENT:
            raise ContextPersistenceError("SOURCE_CLASS_MISMATCH")

    if inp.health_data_id is not None:
        hd = db.query(models.HealthData).filter(models.HealthData.id == int(inp.health_data_id)).first()
        if hd is None:
            raise ContextPersistenceError("HEALTHDATA_NOT_FOUND")
        if int(inp.source_row_id) != int(hd.id):
            raise ContextPersistenceError("SOURCE_ROW_MISMATCH")
        if inp.source_class != SOURCE_LEGACY_HEALTHDATA:
            raise ContextPersistenceError("SOURCE_CLASS_MISMATCH")

    if not _has_any_authoritative_value(inp) and not inp.context_authority:
        return None

    occurrence = build_occurrence_key(
        source_class=inp.source_class,
        source_row_id=inp.source_row_id,
        metric=inp.metric,
    )
    authority_json = json.dumps(inp.context_authority or {}, separators=(",", ":"), sort_keys=True)

    existing = (
        db.query(models.I9VitalObservationContext)
        .filter(models.I9VitalObservationContext.occurrence_key == occurrence)
        .first()
    )
    if existing is not None:
        if int(existing.health_subject_id) != int(inp.health_subject_id):
            raise ContextPersistenceError("SUBJECT_MISMATCH_EXISTING")
        # Idempotent refresh of authoritative fields only (no invented fills).
        if inp.quality_state not in (None, ""):
            existing.quality_state = inp.quality_state
        if inp.activity_state not in (None, ""):
            existing.activity_state = inp.activity_state
        if inp.altitude_value is not None:
            existing.altitude_value = float(inp.altitude_value)
            existing.altitude_unit = inp.altitude_unit
        if inp.temperature_method not in (None, ""):
            existing.temperature_method = inp.temperature_method
        if inp.confirmation_state not in (None, ""):
            existing.confirmation_state = inp.confirmation_state
        if inp.context_authority:
            existing.context_authority_json = authority_json
        if commit:
            db.commit()
            db.refresh(existing)
        else:
            db.flush()
        return existing

    row = models.I9VitalObservationContext(
        health_subject_id=int(inp.health_subject_id),
        source_class=inp.source_class,
        source_row_id=int(inp.source_row_id),
        physiological_measurement_id=inp.physiological_measurement_id,
        health_data_id=inp.health_data_id,
        metric=inp.metric,
        observed_at=_as_utc(inp.observed_at),
        activity_state=inp.activity_state,
        altitude_value=inp.altitude_value,
        altitude_unit=inp.altitude_unit,
        temperature_method=inp.temperature_method,
        quality_state=inp.quality_state,
        confirmation_state=inp.confirmation_state,
        context_authority_json=authority_json if inp.context_authority else None,
        occurrence_key=occurrence,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def load_vital_observation_context_row(
    db: Session,
    *,
    source_class: str,
    source_row_id: int,
    metric: str,
) -> Optional[models.I9VitalObservationContext]:
    occurrence = build_occurrence_key(
        source_class=source_class,
        source_row_id=source_row_id,
        metric=metric,
    )
    return (
        db.query(models.I9VitalObservationContext)
        .filter(models.I9VitalObservationContext.occurrence_key == occurrence)
        .first()
    )


def persist_context_from_physiological_measurement(
    db: Session,
    pm: models.PhysiologicalMeasurement,
    *,
    commit: bool = False,
) -> Optional[models.I9VitalObservationContext]:
    """Persist device-path quality for THIS PM only. Other fields stay NULL/UNKNOWN."""
    if pm.health_subject_id is None:
        return None
    quality = pm.quality_state
    if quality in (None, ""):
        return None
    return persist_vital_observation_context(
        db,
        ContextPersistInput(
            health_subject_id=int(pm.health_subject_id),
            source_class=SOURCE_PHYSIOLOGICAL_MEASUREMENT,
            source_row_id=int(pm.id),
            physiological_measurement_id=int(pm.id),
            metric=str(pm.measurement_type),
            observed_at=pm.measured_at,
            quality_state=str(quality),
            context_authority={
                "quality_source": "physiological_measurements.quality_state",
                "device_id": int(pm.device_id) if pm.device_id is not None else None,
                "activity_source": "NOT_AVAILABLE",
                "altitude_source": "NOT_AVAILABLE",
                "temperature_method_source": "NOT_AVAILABLE",
                "confirmation_source": "NOT_IMPLEMENTED",
            },
        ),
        commit=commit,
    )


def apply_persisted_row_to_context(
    base: VitalObservationContext,
    row: Optional[models.I9VitalObservationContext],
) -> VitalObservationContext:
    """Merge persisted authoritative fields into a VitalObservationContext (fail closed)."""
    if row is None:
        return base

    activity = base.activity_state
    altitude = base.altitude
    temp_method = base.temperature_method
    quality = base.quality_state
    confirmation = base.confirmation_state
    diagnostics = dict(base.diagnostics or {})
    diagnostics["persisted_context_id"] = int(row.id)
    diagnostics["persisted_occurrence_key"] = row.occurrence_key

    if row.activity_state not in (None, ""):
        activity = _known(row.activity_state, source="i9_vital_observation_contexts.activity_state")
    if row.altitude_value is not None:
        altitude = _known(
            {"value": float(row.altitude_value), "unit": row.altitude_unit},
            source="i9_vital_observation_contexts.altitude",
        )
    if row.temperature_method not in (None, ""):
        temp_method = _known(
            row.temperature_method,
            source="i9_vital_observation_contexts.temperature_method",
        )
    if row.quality_state not in (None, ""):
        quality = _known(
            row.quality_state,
            source="i9_vital_observation_contexts.quality_state",
        )
    if row.confirmation_state not in (None, "", "UNCONFIRMED", "UNKNOWN"):
        confirmation = _known(
            row.confirmation_state,
            source="i9_vital_observation_contexts.confirmation_state",
        )

    return VitalObservationContext(
        activity_state=activity,
        symptom_refs=base.symptom_refs,
        altitude=altitude,
        temperature_method=temp_method,
        quality_state=quality,
        confirmation_state=confirmation,
        medication_context=base.medication_context,
        diagnostics=diagnostics,
    )
