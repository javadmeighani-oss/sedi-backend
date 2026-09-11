"""Canonical I9 heart-rate stability — single governed status for I10.

MAD / personal baseline = evidence only. Not clinical safety. Not diagnosis.
STABLE != medically safe. UNSTABLE_OR_CHANGED != emergency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.services.i9.nonclinical_vital_stability import (
    NonclinicalVitalMonitoringStatus,
    NonclinicalVitalStabilityResult,
    evaluate_nonclinical_heart_rate_stability,
)


class CanonicalHrStabilityStatus(str, Enum):
    STABLE = "STABLE"
    UNSTABLE_OR_CHANGED = "UNSTABLE_OR_CHANGED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class CanonicalHrStabilityResult:
    status: CanonicalHrStabilityStatus
    health_subject_id: int
    reason: str
    evidence: NonclinicalVitalStabilityResult
    signal_scope: str = "heart_rate"


def _map_mad(mad: NonclinicalVitalStabilityResult) -> CanonicalHrStabilityStatus:
    if mad.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_STABLE:
        return CanonicalHrStabilityStatus.STABLE
    if mad.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_CHANGED:
        return CanonicalHrStabilityStatus.UNSTABLE_OR_CHANGED
    return CanonicalHrStabilityStatus.INSUFFICIENT_DATA


def evaluate_canonical_hr_stability(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
) -> CanonicalHrStabilityResult:
    """Sole I9 HR stability authority used by I10 daily/instability seams."""
    mad = evaluate_nonclinical_heart_rate_stability(
        db, health_subject_id=int(health_subject_id), when=when
    )
    return CanonicalHrStabilityResult(
        status=_map_mad(mad),
        health_subject_id=int(health_subject_id),
        reason=mad.reason,
        evidence=mad,
        signal_scope=mad.signal_scope or "heart_rate",
    )
