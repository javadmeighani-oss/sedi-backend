"""I4 device safety input contract + fail-closed acceptance (no DB).

Patient identity = canonical HealthSubject only.
Raw DevicePacket is never accepted as evaluated safety evidence.
Binding/device facts must be supplied by the boundary; I4 does not query DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# Infrastructure freshness window only — NOT a clinical/physiological threshold.
DEFAULT_INFRA_FRESHNESS_MAX_AGE = timedelta(hours=24)

SUPPORTED_EVIDENCE_TYPES = frozenset(
    {
        "heart_rate",
        "blood_pressure",
        "glucose",
        "temperature",
        "spo2",
        "device_reported_cardiac_event",
        "test_synthetic",  # test-only evidence type; no clinical meaning
    }
)

_REQUIRED_UNITS = {
    "heart_rate": frozenset({"bpm"}),
    "spo2": frozenset({"%", "percent"}),
    "temperature": frozenset({"c", "celsius", "f", "fahrenheit"}),
    "glucose": frozenset({"mg/dl", "mmol/l"}),
    "blood_pressure": frozenset({"mmhg"}),
}

_ACCEPTABLE_QUALITY = frozenset(
    {
        "ok",
        "good",
        "acceptable",
        "device_packet",
        "device_ingest",
    }
)

_REJECT_QUALITY = frozenset(
    {
        "bad",
        "low",
        "poor",
        "insufficient",
        "corrupt",
        "unknown",
    }
)

FRESH = "FRESH"
STALE = "STALE"
UNKNOWN_FRESHNESS = "UNKNOWN"

NO_DATA_SEMANTIC = "no_data"
INACTIVITY_SEMANTIC = "inactivity"
RAW_PACKET_KIND = "raw_packet"


@dataclass(frozen=True)
class DeviceBindingFacts:
    """Boundary-resolved binding state at observed_at (I4 never loads this)."""

    device_id: Optional[int]
    binding_id: Optional[int]
    binding_health_subject_id: Optional[int]
    binding_active: bool


@dataclass(frozen=True)
class I4DeviceSafetyInput:
    """Normalized subject-native device evidence for I4 evaluation only."""

    health_subject_id: int
    evidence_type: str
    observed_at: Optional[datetime]
    source_class: Optional[str]
    quality_state: Optional[str]
    freshness_state: str
    device_id: Optional[int]
    binding_id: Optional[int]
    binding_active: bool
    binding_health_subject_id: Optional[int]
    evidence_ref: Optional[str]
    provenance_ref: Optional[str]
    unit: Optional[str] = None
    normalized_value: Optional[float] = None
    semantic_state: Optional[str] = None
    received_at: Optional[datetime] = None
    evidence_kind: str = "normalized"
    is_normalized: bool = True


@dataclass(frozen=True)
class DeviceSafetyAcceptance:
    ok: bool
    reason: str


def derive_freshness_state(
    *,
    observed_at: Optional[datetime],
    now: Optional[datetime] = None,
    max_age: timedelta = DEFAULT_INFRA_FRESHNESS_MAX_AGE,
) -> str:
    """Infrastructure freshness marker — not a clinical acuity judgment."""
    if observed_at is None:
        return UNKNOWN_FRESHNESS
    ref = now or datetime.now(timezone.utc)
    obs = observed_at
    if obs.tzinfo is None:
        obs = obs.replace(tzinfo=timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    age = ref - obs
    if age < timedelta(0):
        # Future timestamps are not trustworthy for safety evaluation.
        return UNKNOWN_FRESHNESS
    if age > max_age:
        return STALE
    return FRESH


def accept_device_safety_input(inp: I4DeviceSafetyInput) -> DeviceSafetyAcceptance:
    """Fail-closed acceptance firewall before I4 rule evaluation."""
    if not isinstance(inp.health_subject_id, int) or inp.health_subject_id <= 0:
        return DeviceSafetyAcceptance(False, "missing_or_invalid_health_subject_id")

    if not inp.is_normalized or inp.evidence_kind == RAW_PACKET_KIND:
        return DeviceSafetyAcceptance(False, "raw_or_unnormalized_packet")

    if not isinstance(inp.evidence_type, str) or not inp.evidence_type.strip():
        return DeviceSafetyAcceptance(False, "unsupported_evidence_type")
    et = inp.evidence_type.strip().lower()
    if et not in SUPPORTED_EVIDENCE_TYPES:
        return DeviceSafetyAcceptance(False, "unsupported_evidence_type")

    sem = (inp.semantic_state or "").strip().lower()
    if sem == NO_DATA_SEMANTIC:
        return DeviceSafetyAcceptance(False, "no_data")
    if sem == INACTIVITY_SEMANTIC:
        return DeviceSafetyAcceptance(False, "inactivity_only")

    if inp.observed_at is None:
        return DeviceSafetyAcceptance(False, "missing_timestamp")

    if inp.freshness_state == STALE:
        return DeviceSafetyAcceptance(False, "stale_evidence")
    if inp.freshness_state != FRESH:
        return DeviceSafetyAcceptance(False, "insufficient_freshness")

    if not inp.source_class or not str(inp.source_class).strip():
        return DeviceSafetyAcceptance(False, "missing_provenance")
    if not inp.evidence_ref or not str(inp.evidence_ref).strip():
        return DeviceSafetyAcceptance(False, "missing_provenance")
    if not inp.provenance_ref or not str(inp.provenance_ref).strip():
        return DeviceSafetyAcceptance(False, "missing_provenance")

    qs = (inp.quality_state or "").strip().lower()
    if not qs:
        return DeviceSafetyAcceptance(False, "insufficient_quality")
    if qs in _REJECT_QUALITY or qs not in _ACCEPTABLE_QUALITY:
        return DeviceSafetyAcceptance(False, "insufficient_quality")

    # Device-bound evidence requires an active binding to the claimed subject.
    if inp.device_id is not None:
        if not inp.binding_active:
            return DeviceSafetyAcceptance(False, "unbound_or_inactive_binding")
        if inp.binding_health_subject_id is None:
            return DeviceSafetyAcceptance(False, "unbound_device")
        if int(inp.binding_health_subject_id) != int(inp.health_subject_id):
            return DeviceSafetyAcceptance(False, "wrong_subject_binding")
        if inp.binding_id is None:
            return DeviceSafetyAcceptance(False, "unbound_device")

    required_units = _REQUIRED_UNITS.get(et)
    if required_units is not None:
        if not inp.unit or not str(inp.unit).strip():
            return DeviceSafetyAcceptance(False, "missing_required_unit")
        if str(inp.unit).strip().lower() not in required_units:
            return DeviceSafetyAcceptance(False, "unknown_unit")

    if inp.normalized_value is None and not sem:
        return DeviceSafetyAcceptance(False, "no_data")

    return DeviceSafetyAcceptance(True, "accepted")


def build_i4_device_safety_input(
    *,
    health_subject_id: int,
    evidence_type: str,
    observed_at: Optional[datetime],
    source_class: Optional[str],
    quality_state: Optional[str],
    device_id: Optional[int],
    binding: DeviceBindingFacts,
    evidence_ref: Optional[str],
    provenance_ref: Optional[str],
    unit: Optional[str] = None,
    normalized_value: Optional[float] = None,
    semantic_state: Optional[str] = None,
    received_at: Optional[datetime] = None,
    evidence_kind: str = "normalized",
    is_normalized: bool = True,
    now: Optional[datetime] = None,
    max_age: timedelta = DEFAULT_INFRA_FRESHNESS_MAX_AGE,
) -> I4DeviceSafetyInput:
    """Construct input with derived infrastructure freshness (no DB)."""
    freshness = derive_freshness_state(observed_at=observed_at, now=now, max_age=max_age)
    return I4DeviceSafetyInput(
        health_subject_id=health_subject_id,
        evidence_type=evidence_type,
        observed_at=observed_at,
        source_class=source_class,
        quality_state=quality_state,
        freshness_state=freshness,
        device_id=device_id,
        binding_id=binding.binding_id,
        binding_active=binding.binding_active,
        binding_health_subject_id=binding.binding_health_subject_id,
        evidence_ref=evidence_ref,
        provenance_ref=provenance_ref,
        unit=unit,
        normalized_value=normalized_value,
        semantic_state=semantic_state,
        received_at=received_at,
        evidence_kind=evidence_kind,
        is_normalized=is_normalized,
    )
