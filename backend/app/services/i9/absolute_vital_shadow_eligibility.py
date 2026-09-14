"""I9 absolute-vital NONNUMERIC shadow eligibility (G9).

Answers only whether an observation is sufficiently governed for a FUTURE
numeric absolute-vitals policy evaluator.

NOT clinical interpretation. NOT alert generation. NO I10 / Notification side effects.
Does NOT persist governed absolute alert result rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.services.i9.absolute_vital_observation import (
    SUPPORTED_METRICS,
    CanonicalVitalObservation,
)

if TYPE_CHECKING:
    from backend.app import models as _models

# Operational eligibility states — not clinical statuses.
ELIGIBLE_FOR_FUTURE_NUMERIC_EVALUATION = "ELIGIBLE_FOR_FUTURE_NUMERIC_EVALUATION"
BLOCKED_POLICY_NOT_APPROVED = "BLOCKED_POLICY_NOT_APPROVED"
BLOCKED_SUBJECT_AUTHORITY = "BLOCKED_SUBJECT_AUTHORITY"
BLOCKED_PROVENANCE = "BLOCKED_PROVENANCE"
BLOCKED_UNIT_AUTHORITY = "BLOCKED_UNIT_AUTHORITY"
BLOCKED_MEASUREMENT_QUALITY = "BLOCKED_MEASUREMENT_QUALITY"
BLOCKED_CONFIRMATION = "BLOCKED_CONFIRMATION"
BLOCKED_MISSING_CONTEXT = "BLOCKED_MISSING_CONTEXT"
BLOCKED_UNSUPPORTED_METRIC = "BLOCKED_UNSUPPORTED_METRIC"
BLOCKED_INVALID_STRUCTURAL_VALUE = "BLOCKED_INVALID_STRUCTURAL_VALUE"

# Metric-required context keys that MUST come from governed authority (never invented).
_REQUIRED_CONTEXT_KEYS: dict[str, tuple[str, ...]] = {
    "heart_rate": ("resting_or_activity_or_sleep",),
    "spo2": ("symptoms", "altitude_or_baseline"),
    "temperature": ("measurement_site_or_method",),
}

# G9: numeric absolute policy is not PO-approved; do not treat draft scaffold rows as authority.
NUMERIC_POLICY_AUTHORIZED = False


@dataclass(frozen=True)
class ObservationEligibility:
    metric: str
    blockers: tuple[str, ...]
    observation: CanonicalVitalObservation


@dataclass(frozen=True)
class ShadowEligibilityResult:
    """Batch shadow eligibility — diagnostics only; no persistence side effects."""

    observations: tuple[ObservationEligibility, ...]
    blockers: tuple[str, ...]
    final_state: str
    numeric_policy_authorized: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def eligible(self) -> bool:
        return self.final_state == ELIGIBLE_FOR_FUTURE_NUMERIC_EVALUATION


def _context_present(observation: CanonicalVitalObservation) -> bool:
    """Context is present only if provenance already carries governed context facts.

    G9 does not invent resting/activity/sleep/symptoms/altitude/site.
    """
    ctx = observation.provenance.get("context")
    if not isinstance(ctx, dict):
        return False
    required = _REQUIRED_CONTEXT_KEYS.get(observation.metric, ())
    return all(ctx.get(key) not in (None, "", False) for key in required)


def _confirmation_present(observation: CanonicalVitalObservation) -> bool:
    """Confirmation only if an explicit governed confirmation authority is attached.

    G9 does not infer confirmation from multiple HealthData rows.
    """
    return observation.provenance.get("confirmation_authority") not in (None, "", False)


def _quality_present(observation: CanonicalVitalObservation) -> bool:
    return observation.quality_state not in (None, "")


def _provenance_present(observation: CanonicalVitalObservation) -> bool:
    prov = observation.provenance or {}
    if prov.get("health_data_id") is not None:
        return True
    if prov.get("physiological_measurement_id") is not None:
        return True
    if prov.get("device_packet_id") is not None:
        return True
    return False


def _unit_present(observation: CanonicalVitalObservation) -> bool:
    return observation.unit not in (None, "") and bool(
        observation.provenance.get("unit_authority")
    )


def evaluate_observation_eligibility(
    observation: CanonicalVitalObservation,
) -> ObservationEligibility:
    blockers: list[str] = []

    if observation.metric not in SUPPORTED_METRICS:
        blockers.append(BLOCKED_UNSUPPORTED_METRIC)

    if not observation.structural_parse_ok or observation.normalized_value is None:
        blockers.append(BLOCKED_INVALID_STRUCTURAL_VALUE)

    if observation.health_subject_id is None:
        blockers.append(BLOCKED_SUBJECT_AUTHORITY)

    if not _provenance_present(observation):
        blockers.append(BLOCKED_PROVENANCE)

    if not _unit_present(observation):
        blockers.append(BLOCKED_UNIT_AUTHORITY)

    if not _quality_present(observation):
        blockers.append(BLOCKED_MEASUREMENT_QUALITY)

    if not _confirmation_present(observation):
        blockers.append(BLOCKED_CONFIRMATION)

    if not _context_present(observation):
        blockers.append(BLOCKED_MISSING_CONTEXT)

    return ObservationEligibility(
        metric=observation.metric,
        blockers=tuple(dict.fromkeys(blockers)),
        observation=observation,
    )


def _approved_numeric_policy_exists(db: Session) -> bool:
    """G9: numeric policy is not authorized. Scaffold draft rows do not count.

    Future gates may query approved policy-authority rows; G9 must not
    treat unseeded/draft scaffold tables as authority.
    """
    _ = db  # session retained for future approved-policy lookup signature
    return bool(NUMERIC_POLICY_AUTHORIZED)


def evaluate_shadow_eligibility(
    db: Session,
    observations: Sequence[CanonicalVitalObservation],
) -> ShadowEligibilityResult:
    """Fail-closed nonnumeric shadow eligibility. No DB writes. No notifications."""
    per = tuple(evaluate_observation_eligibility(obs) for obs in observations)
    blockers: list[str] = []
    for item in per:
        blockers.extend(item.blockers)

    numeric_ok = _approved_numeric_policy_exists(db)
    if not numeric_ok:
        blockers.append(BLOCKED_POLICY_NOT_APPROVED)

    # Deduplicate preserving order
    blockers_t = tuple(dict.fromkeys(blockers))

    if blockers_t:
        # Prefer policy blocker as final when it is the sole remaining gate after
        # nonnumeric prerequisites; otherwise report aggregate blocked state as
        # the first blocker (deterministic) while retaining full list.
        if blockers_t == (BLOCKED_POLICY_NOT_APPROVED,):
            final_state = BLOCKED_POLICY_NOT_APPROVED
        elif BLOCKED_POLICY_NOT_APPROVED in blockers_t and len(blockers_t) > 1:
            # Nonnumeric gaps dominate messaging; policy still recorded in blockers.
            final_state = blockers_t[0]
        else:
            final_state = blockers_t[0]
    else:
        final_state = ELIGIBLE_FOR_FUTURE_NUMERIC_EVALUATION

    return ShadowEligibilityResult(
        observations=per,
        blockers=blockers_t,
        final_state=final_state,
        numeric_policy_authorized=bool(numeric_ok),
        diagnostics={
            "shadow_eligibility_only": True,
            "clinical_interpreter": False,
            "numeric_policy_status": "NOT_APPROVED",
            "i10_side_effects": False,
            "alert_results_persisted": False,
            "observation_count": len(per),
        },
    )


def evaluate_health_data_shadow_eligibility(
    db: Session,
    health_data: "_models.HealthData",
) -> ShadowEligibilityResult:
    """Convenience: adapt HealthData then evaluate shadow eligibility (no side effects)."""
    from backend.app.services.i9.absolute_vital_observation import (
        adapt_health_data_to_observations,
    )

    observations = adapt_health_data_to_observations(db, health_data)
    return evaluate_shadow_eligibility(db, observations)
