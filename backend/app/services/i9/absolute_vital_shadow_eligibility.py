"""I9 absolute-vital NONNUMERIC shadow eligibility (G9 + G11 context).

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
from backend.app.services.i9.vital_observation_context import (
    AuthorityState,
    VitalObservationContext,
    attach_context_to_observations,
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

# G9/G11: numeric absolute policy is not PO-approved.
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


def _context_object(observation: CanonicalVitalObservation) -> Optional[VitalObservationContext]:
    ctx = (observation.provenance or {}).get("context_object")
    return ctx if isinstance(ctx, VitalObservationContext) else None


def _metric_context_satisfied(
    observation: CanonicalVitalObservation,
    ctx: Optional[VitalObservationContext],
) -> bool:
    """Required metric context must be KNOWN from VitalObservationContext — never invented."""
    if ctx is None:
        # Legacy provenance.context dict path (G9 tests) — still require explicit keys.
        legacy = observation.provenance.get("context")
        if not isinstance(legacy, dict):
            return False
        required = {
            "heart_rate": ("resting_or_activity_or_sleep",),
            "spo2": ("symptoms", "altitude_or_baseline"),
            "temperature": ("measurement_site_or_method",),
        }.get(observation.metric, ())
        return all(legacy.get(key) not in (None, "", False) for key in required)

    if observation.metric == "heart_rate":
        return ctx.activity_state.state == AuthorityState.KNOWN
    if observation.metric == "spo2":
        return (
            ctx.symptom_refs.state == AuthorityState.KNOWN
            and ctx.altitude.state == AuthorityState.KNOWN
        )
    if observation.metric == "temperature":
        return ctx.temperature_method.state == AuthorityState.KNOWN
    return False


def _confirmation_present(
    observation: CanonicalVitalObservation,
    ctx: Optional[VitalObservationContext],
) -> bool:
    if ctx is not None:
        # UNKNOWN / UNCONFIRMED structural value is not confirmation authority.
        if ctx.confirmation_state.state != AuthorityState.KNOWN:
            return False
        value = ctx.confirmation_state.value
        if value in (None, "", "UNCONFIRMED", "UNKNOWN"):
            return False
        return True
    return observation.provenance.get("confirmation_authority") not in (None, "", False)


def _quality_present(
    observation: CanonicalVitalObservation,
    ctx: Optional[VitalObservationContext],
) -> bool:
    if ctx is not None:
        return ctx.quality_state.state == AuthorityState.KNOWN
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
    ctx = _context_object(observation)

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

    if not _quality_present(observation, ctx):
        blockers.append(BLOCKED_MEASUREMENT_QUALITY)

    if not _confirmation_present(observation, ctx):
        blockers.append(BLOCKED_CONFIRMATION)

    if not _metric_context_satisfied(observation, ctx):
        blockers.append(BLOCKED_MISSING_CONTEXT)

    return ObservationEligibility(
        metric=observation.metric,
        blockers=tuple(dict.fromkeys(blockers)),
        observation=observation,
    )


def _approved_numeric_policy_exists(db: Session) -> bool:
    _ = db
    return bool(NUMERIC_POLICY_AUTHORIZED)


def evaluate_shadow_eligibility(
    db: Session,
    observations: Sequence[CanonicalVitalObservation],
    *,
    attach_context: bool = True,
) -> ShadowEligibilityResult:
    """Fail-closed nonnumeric shadow eligibility. No DB writes. No notifications."""
    prepared: Sequence[CanonicalVitalObservation] = observations
    if attach_context:
        prepared = attach_context_to_observations(db, observations)

    per = tuple(evaluate_observation_eligibility(obs) for obs in prepared)
    blockers: list[str] = []
    for item in per:
        blockers.extend(item.blockers)

    numeric_ok = _approved_numeric_policy_exists(db)
    if not numeric_ok:
        blockers.append(BLOCKED_POLICY_NOT_APPROVED)

    blockers_t = tuple(dict.fromkeys(blockers))

    if blockers_t:
        if blockers_t == (BLOCKED_POLICY_NOT_APPROVED,):
            final_state = BLOCKED_POLICY_NOT_APPROVED
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
            "vital_observation_context": True,
            "context_attached": bool(attach_context),
        },
    )


def evaluate_health_data_shadow_eligibility(
    db: Session,
    health_data: "_models.HealthData",
) -> ShadowEligibilityResult:
    """Convenience: adapt HealthData, attach context, evaluate shadow eligibility."""
    from backend.app.services.i9.absolute_vital_observation import (
        adapt_health_data_to_observations,
    )

    observations = adapt_health_data_to_observations(db, health_data)
    return evaluate_shadow_eligibility(db, observations, attach_context=True)
