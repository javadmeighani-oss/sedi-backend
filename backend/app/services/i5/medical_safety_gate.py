"""I5-IMPL-W2-P02 — medical-safety transition / human-review gate (no DB)."""
from __future__ import annotations

from typing import Union

from backend.app.services.i5.enums import ConflictState, MedicalSafetyState

_HIGH_RISK_DOMAIN_TOKENS: frozenset[str] = frozenset(
    {
        "diabetes",
        "pregnancy",
        "pediatrics",
        "emergency",
        "medication",
        "contraindication",
        "cardiology",
        "neurology",
        "infectious",
        "mental_health_crisis",
    }
)

_ALLOWED_MEDICAL_SAFETY_TRANSITIONS: frozenset[
    tuple[MedicalSafetyState, MedicalSafetyState]
] = frozenset(
    {
        (MedicalSafetyState.UNKNOWN, MedicalSafetyState.UNKNOWN),
        (MedicalSafetyState.UNKNOWN, MedicalSafetyState.PENDING_REVIEW),
        (MedicalSafetyState.PENDING_REVIEW, MedicalSafetyState.PENDING_REVIEW),
        (MedicalSafetyState.PENDING_REVIEW, MedicalSafetyState.CLEARED),
        (MedicalSafetyState.PENDING_REVIEW, MedicalSafetyState.RESTRICTED),
        (MedicalSafetyState.PENDING_REVIEW, MedicalSafetyState.BLOCKED),
        (MedicalSafetyState.CLEARED, MedicalSafetyState.CLEARED),
        (MedicalSafetyState.CLEARED, MedicalSafetyState.RESTRICTED),
        (MedicalSafetyState.CLEARED, MedicalSafetyState.BLOCKED),
        (MedicalSafetyState.CLEARED, MedicalSafetyState.PENDING_REVIEW),
        (MedicalSafetyState.RESTRICTED, MedicalSafetyState.RESTRICTED),
        (MedicalSafetyState.RESTRICTED, MedicalSafetyState.BLOCKED),
        (MedicalSafetyState.RESTRICTED, MedicalSafetyState.PENDING_REVIEW),
        (MedicalSafetyState.RESTRICTED, MedicalSafetyState.CLEARED),
        (MedicalSafetyState.BLOCKED, MedicalSafetyState.BLOCKED),
        (MedicalSafetyState.BLOCKED, MedicalSafetyState.PENDING_REVIEW),
    }
)


class MedicalSafetyGateError(ValueError):
    """Fail-closed validation error for medical-safety helpers."""


def _coerce_medical_safety(value: Union[str, MedicalSafetyState]) -> MedicalSafetyState:
    if isinstance(value, MedicalSafetyState):
        return value
    try:
        return MedicalSafetyState(str(value))
    except ValueError as exc:
        raise MedicalSafetyGateError(f"MEDICAL_SAFETY_STATE_INVALID:{value}") from exc


def _coerce_conflict(value: Union[str, ConflictState, None]) -> ConflictState | None:
    if value is None:
        return None
    if isinstance(value, ConflictState):
        return value
    try:
        return ConflictState(str(value))
    except ValueError as exc:
        raise MedicalSafetyGateError(f"CONFLICT_STATE_INVALID:{value}") from exc


def assert_allowed_medical_safety_transition(
    old: Union[str, MedicalSafetyState],
    new: Union[str, MedicalSafetyState],
) -> None:
    """Fail-closed medical-safety transition guard (no BLOCKED→CLEARED direct)."""
    old_state = _coerce_medical_safety(old)
    new_state = _coerce_medical_safety(new)
    if (old_state, new_state) not in _ALLOWED_MEDICAL_SAFETY_TRANSITIONS:
        raise MedicalSafetyGateError(
            f"ILLEGAL_MEDICAL_SAFETY_TRANSITION:{old_state.value}->{new_state.value}"
        )


def domain_is_high_risk(domain: str) -> bool:
    """True when domain casefold-contains any frozen high-risk token."""
    sample = (domain or "").casefold()
    if not sample:
        return False
    return any(token in sample for token in _HIGH_RISK_DOMAIN_TOKENS)


def requires_human_review(
    domain: str,
    medical_safety_state: Union[str, MedicalSafetyState],
    conflict_state: Union[str, ConflictState, None],
    high_risk: bool,
) -> bool:
    """Whether human medical-safety review is required (fail-closed)."""
    state = _coerce_medical_safety(medical_safety_state)
    conflict = _coerce_conflict(conflict_state)
    risk = bool(high_risk) or domain_is_high_risk(domain)
    if state in (
        MedicalSafetyState.PENDING_REVIEW,
        MedicalSafetyState.RESTRICTED,
        MedicalSafetyState.BLOCKED,
    ):
        return True
    if conflict in (ConflictState.SUSPECTED, ConflictState.CONFIRMED):
        return True
    if risk and state != MedicalSafetyState.CLEARED:
        return True
    return False


def should_enqueue_safety_review(
    domain: str,
    medical_safety_state: Union[str, MedicalSafetyState],
    conflict_state: Union[str, ConflictState, None],
    high_risk: bool,
) -> bool:
    """Enqueue when human review is required and safety is not CLEARED."""
    state = _coerce_medical_safety(medical_safety_state)
    if state is MedicalSafetyState.CLEARED:
        return False
    return requires_human_review(domain, state, conflict_state, high_risk)
