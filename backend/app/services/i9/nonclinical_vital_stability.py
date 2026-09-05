"""I9 nonclinical heart-rate personal-pattern stability (Product Owner MAD band).

NOT clinical safety. NOT diagnosis. I4 remains sole clinical authority.
STABLE != healthy/safe. CHANGED != emergency/danger.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.baseline_service import (
    BASELINE_METHOD,
    BASELINE_SCOPE_V1,
    compute_daily_median_for_subject,
)
from backend.app.services.i9.health_subject_service import preferred_language_for_subject
from backend.app.services.i9.i8_projection_service import get_bounded_context_projection_for_subject

# Product Owner Option 1 — frozen constants (do not invent alternatives here).
MAD_SCALE = 1.4826
CHANGE_THRESHOLD_SIGMA = 3
RAW_MAD_MULTIPLIER = 4.4478  # 3 * 1.4826
SIGNAL_SCOPE = BASELINE_SCOPE_V1
_RAW_MAD_MULTIPLIER_DEC = Decimal("4.4478")


class NonclinicalVitalMonitoringStatus(str, Enum):
    NONCLINICAL_STABLE = "NONCLINICAL_STABLE"
    NONCLINICAL_CHANGED = "NONCLINICAL_CHANGED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True)
class NonclinicalVitalStabilityResult:
    status: NonclinicalVitalMonitoringStatus
    signal_scope: str
    baseline_quality: Optional[str]
    daily_median: Optional[float]
    baseline_value: Optional[float]
    dispersion_value: Optional[float]
    delta: Optional[float]
    limit: Optional[float]
    reason: str
    baseline_id: Optional[int] = None
    health_subject_id: Optional[int] = None


def _insufficient(
    *,
    reason: str,
    health_subject_id: Optional[int] = None,
    baseline_quality: Optional[str] = None,
    daily_median: Optional[float] = None,
    baseline_value: Optional[float] = None,
    dispersion_value: Optional[float] = None,
    baseline_id: Optional[int] = None,
) -> NonclinicalVitalStabilityResult:
    return NonclinicalVitalStabilityResult(
        status=NonclinicalVitalMonitoringStatus.DATA_INSUFFICIENT,
        signal_scope=SIGNAL_SCOPE,
        baseline_quality=baseline_quality,
        daily_median=daily_median,
        baseline_value=baseline_value,
        dispersion_value=dispersion_value,
        delta=None,
        limit=None,
        reason=reason,
        baseline_id=baseline_id,
        health_subject_id=health_subject_id,
    )


def _finite_positive(value: Optional[float]) -> bool:
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0.0


def evaluate_nonclinical_heart_rate_stability(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
) -> NonclinicalVitalStabilityResult:
    """Classify personal-pattern monitoring status for heart_rate only.

    Requires ESTABLISHED baseline, MAD > 0, and a current daily median.
    Equal-to-threshold ⇒ NONCLINICAL_STABLE; greater ⇒ NONCLINICAL_CHANGED.
    """
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    subject = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.id == health_subject_id,
            models.HealthSubject.status == "active",
        )
        .first()
    )
    if subject is None:
        return _insufficient(reason="inactive_or_missing_subject", health_subject_id=health_subject_id)

    lang = preferred_language_for_subject(db, subject)
    daily_median = compute_daily_median_for_subject(
        db,
        health_subject_id=health_subject_id,
        measurement_type=SIGNAL_SCOPE,
        ref=when,
        preferred_language=lang,
    )
    if daily_median is None:
        return _insufficient(
            reason="no_current_daily_median",
            health_subject_id=health_subject_id,
        )

    projection = get_bounded_context_projection_for_subject(
        db, health_subject_id=health_subject_id, measurement_type=SIGNAL_SCOPE
    )
    baseline = projection.personal_observed_baseline
    if baseline is None:
        return _insufficient(
            reason="baseline_none",
            health_subject_id=health_subject_id,
            daily_median=daily_median,
        )

    quality = (baseline.quality or "").upper() or None
    if quality != "ESTABLISHED":
        reason = "baseline_provisional" if quality == "PROVISIONAL" else "baseline_not_established"
        return _insufficient(
            reason=reason,
            health_subject_id=health_subject_id,
            baseline_quality=quality,
            daily_median=daily_median,
            baseline_value=baseline.baseline_value,
            dispersion_value=baseline.dispersion_value,
            baseline_id=baseline.baseline_id,
        )

    if baseline.baseline_method and baseline.baseline_method != BASELINE_METHOD:
        return _insufficient(
            reason="baseline_method_unsupported",
            health_subject_id=health_subject_id,
            baseline_quality=quality,
            daily_median=daily_median,
            baseline_id=baseline.baseline_id,
        )

    baseline_value = baseline.baseline_value
    dispersion = baseline.dispersion_value
    if baseline_value is None or not math.isfinite(float(baseline_value)):
        return _insufficient(
            reason="baseline_value_missing",
            health_subject_id=health_subject_id,
            baseline_quality=quality,
            daily_median=daily_median,
            dispersion_value=dispersion,
            baseline_id=baseline.baseline_id,
        )

    if dispersion is None or not math.isfinite(float(dispersion)):
        return _insufficient(
            reason="dispersion_invalid",
            health_subject_id=health_subject_id,
            baseline_quality=quality,
            daily_median=daily_median,
            baseline_value=float(baseline_value),
            dispersion_value=dispersion,
            baseline_id=baseline.baseline_id,
        )

    if float(dispersion) == 0.0:
        return _insufficient(
            reason="mad_zero",
            health_subject_id=health_subject_id,
            baseline_quality=quality,
            daily_median=daily_median,
            baseline_value=float(baseline_value),
            dispersion_value=0.0,
            baseline_id=baseline.baseline_id,
        )

    if not _finite_positive(dispersion):
        return _insufficient(
            reason="dispersion_non_positive",
            health_subject_id=health_subject_id,
            baseline_quality=quality,
            daily_median=daily_median,
            baseline_value=float(baseline_value),
            dispersion_value=float(dispersion),
            baseline_id=baseline.baseline_id,
        )

    delta_dec = abs(Decimal(str(float(daily_median))) - Decimal(str(float(baseline_value))))
    limit_dec = _RAW_MAD_MULTIPLIER_DEC * Decimal(str(float(dispersion)))
    delta = float(delta_dec)
    limit = float(limit_dec)
    # EQUAL_TO_THRESHOLD ⇒ STABLE; tiny Decimal/IEEE residue treated as equal (not a clinical band).
    _eq_eps = Decimal("1e-9")
    if delta_dec <= limit_dec or abs(delta_dec - limit_dec) <= _eq_eps:
        status = NonclinicalVitalMonitoringStatus.NONCLINICAL_STABLE
        reason = "within_mad_band"
    else:
        status = NonclinicalVitalMonitoringStatus.NONCLINICAL_CHANGED
        reason = "outside_mad_band"

    return NonclinicalVitalStabilityResult(
        status=status,
        signal_scope=SIGNAL_SCOPE,
        baseline_quality=quality,
        daily_median=float(daily_median),
        baseline_value=float(baseline_value),
        dispersion_value=float(dispersion),
        delta=delta,
        limit=limit,
        reason=reason,
        baseline_id=baseline.baseline_id,
        health_subject_id=health_subject_id,
    )
