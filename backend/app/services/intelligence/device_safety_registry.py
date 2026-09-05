"""I4 code-governed device safety rule registry (infrastructure shell).

Production active physiological/clinical rules MUST remain empty until a
separate clinical-rule gate approves them. This module is NOT a medical
threshold authority.

Test-only rules and synthetic evidence fixtures MUST NOT live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from backend.app.services.intelligence.contracts import (
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.device_safety_input import I4DeviceSafetyInput

DEVICE_REGISTRY_VERSION = "sedi.safety.device.v1"

# Production active clinical device rules — intentionally empty for S02-IMPL.
ACTIVE_CLINICAL_DEVICE_RULES: tuple["DeviceSafetyRule", ...] = ()


@dataclass(frozen=True)
class DeviceSafetyRule:
    """Infrastructure rule contract. Clinical thresholds must not be populated in production."""

    rule_id: str
    registry_version: str
    evidence_type: str
    required_unit: Optional[str]
    required_quality_states: frozenset[str]
    required_freshness_states: frozenset[str]
    level: RiskLevel
    action: SafetyAction
    domain: RiskDomain
    # Deterministic predicate over already-accepted input. Must not encode medical thresholds
    # in the production registry (production list is empty).
    matches: Callable[[I4DeviceSafetyInput], bool]


def active_clinical_device_rule_count() -> int:
    return len(ACTIVE_CLINICAL_DEVICE_RULES)


def get_active_clinical_device_rules() -> tuple[DeviceSafetyRule, ...]:
    """Return production active rules. Empty until clinical-rule gate."""
    return ACTIVE_CLINICAL_DEVICE_RULES


def assert_production_registry_empty() -> None:
    if active_clinical_device_rule_count() != 0:
        raise RuntimeError("ACTIVE_CLINICAL_DEVICE_RULE_COUNT_MUST_BE_ZERO")


def rule_matches_input(rule: DeviceSafetyRule, inp: I4DeviceSafetyInput) -> bool:
    if rule.evidence_type.strip().lower() != inp.evidence_type.strip().lower():
        return False
    if rule.required_unit is not None:
        if not inp.unit or inp.unit.strip().lower() != rule.required_unit.strip().lower():
            return False
    qs = (inp.quality_state or "").strip().lower()
    if qs not in {s.lower() for s in rule.required_quality_states}:
        return False
    if inp.freshness_state not in rule.required_freshness_states:
        return False
    return bool(rule.matches(inp))


def select_matching_rules(inp: I4DeviceSafetyInput) -> tuple[DeviceSafetyRule, ...]:
    """Match against the governed ACTIVE registry only (no caller-supplied authority)."""
    return tuple(r for r in get_active_clinical_device_rules() if rule_matches_input(r, inp))
