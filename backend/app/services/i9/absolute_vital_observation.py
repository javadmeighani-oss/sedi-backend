"""I9 canonical vital observation contract + HealthData structural adapter (G9).

SHADOW / STRUCTURAL ONLY.
No clinical thresholds, interpretation, alerts, or I10 side effects.
HealthData → PhysiologicalMeasurement dual-write: DEFERRED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.self_producer_adapter import resolve_self_health_subject_id

# I9 PhysiologicalMeasurement + HealthDataAddRequest documented conventions (structural only).
SUPPORTED_METRICS: frozenset[str] = frozenset({"heart_rate", "spo2", "temperature"})
_METRIC_UNIT: dict[str, str] = {
    "heart_rate": "bpm",
    "spo2": "percent",
    "temperature": "C",
}
_HEALTHDATA_FIELD: dict[str, str] = {
    "heart_rate": "heart_rate",
    "spo2": "spo2",
    "temperature": "temperature",
}

SOURCE_CLASS_LEGACY_HEALTHDATA = "LEGACY_HEALTHDATA"


@dataclass(frozen=True)
class CanonicalVitalObservation:
    """Structural vital observation — not a clinical interpretation."""

    metric: str
    normalized_value: Optional[float]
    unit: Optional[str]
    measured_at: Optional[datetime]
    source_class: Optional[str]
    account_user_id: Optional[int]
    health_subject_id: Optional[int]
    device_id: Optional[int]
    quality_state: Optional[str]
    provenance: dict[str, Any] = field(default_factory=dict)
    structural_parse_ok: bool = False


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_structural_float(raw: Any) -> tuple[Optional[float], bool]:
    """Parse structural numeric only — no range/clinical validation."""
    if raw is None:
        return None, False
    if isinstance(raw, bool):
        return None, False
    try:
        text = str(raw).strip()
        if text == "":
            return None, False
        value = float(text)
    except (TypeError, ValueError):
        return None, False
    if value != value:  # NaN
        return None, False
    return value, True


def adapt_health_data_to_observations(
    db: Session,
    health_data: models.HealthData,
    *,
    metrics: Optional[Sequence[str]] = None,
) -> list[CanonicalVitalObservation]:
    """Map a HealthData row to structural CanonicalVitalObservation list.

    Does not dual-write PhysiologicalMeasurement (DEFERRED).
    Does not interpret clinical meaning.
    Resolves SELF HealthSubject via existing resolver only (no ensure, no OTHER inference).
    """
    wanted = list(metrics) if metrics is not None else list(SUPPORTED_METRICS)
    account_user_id = int(health_data.user_id) if health_data.user_id is not None else None
    subject_id = (
        resolve_self_health_subject_id(db, account_user_id)
        if account_user_id is not None
        else None
    )
    measured_at = _as_utc(health_data.created_at)
    health_data_id = int(health_data.id) if health_data.id is not None else None

    out: list[CanonicalVitalObservation] = []
    for metric in wanted:
        if metric not in SUPPORTED_METRICS:
            out.append(
                CanonicalVitalObservation(
                    metric=metric,
                    normalized_value=None,
                    unit=None,
                    measured_at=measured_at,
                    source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
                    account_user_id=account_user_id,
                    health_subject_id=subject_id,
                    device_id=None,
                    quality_state=None,
                    provenance={
                        "health_data_id": health_data_id,
                        "adapter": "health_data_structural_v1",
                        "unsupported_metric": True,
                    },
                    structural_parse_ok=False,
                )
            )
            continue

        attr = _HEALTHDATA_FIELD[metric]
        raw = getattr(health_data, attr, None)
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            continue

        value, ok = _parse_structural_float(raw)
        unit = _METRIC_UNIT[metric] if ok else None
        out.append(
            CanonicalVitalObservation(
                metric=metric,
                normalized_value=value if ok else None,
                unit=unit,
                measured_at=measured_at,
                source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
                account_user_id=account_user_id,
                health_subject_id=subject_id,
                device_id=None,
                quality_state=None,  # HealthData has no quality authority
                provenance={
                    "health_data_id": health_data_id,
                    "adapter": "health_data_structural_v1",
                    "source_field": attr,
                    "raw_value": str(raw),
                    "timestamp_source": "health_data.created_at",
                    "unit_authority": "legacy_healthdata_api_and_i9_pm_convention",
                    "quality_authority": None,
                    "confirmation_authority": None,
                    "context_authority": None,
                    "healthdata_pm_dual_write": "DEFERRED",
                },
                structural_parse_ok=ok,
            )
        )
    return out
