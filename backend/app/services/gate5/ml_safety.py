"""Gate 5-E/F/G — ML output safety validation (V1 non-diagnostic boundary)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

ALLOWED_OUTPUT_TYPES = frozenset(
    {
        "possible_anomaly",
        "unusual_pattern",
        "signal_quality_issue",
        "needs_review",
        "low_confidence",
        "insufficient_data",
        "care_suggestion_candidate",
    }
)

ALLOWED_MODEL_STATUSES = frozenset({"research", "shadow", "active", "retired"})

ALLOWED_SIGNAL_FAMILIES = frozenset({"heart", "ecg", "heart_rate"})

ALLOWED_INPUT_TYPES = frozenset(
    {
        "raw_signal_features",
        "raw_signal_window",
        "rr_intervals",
        "hrv_features",
    }
)

ALLOWED_SAFETY_STATUSES = frozenset({"shadow_only", "internal_review", "blocked_clinical"})

FORBIDDEN_OUTPUT_TYPES = frozenset(
    {
        "diagnosis",
        "arrhythmia",
        "disease",
        "emergency",
        "medication",
        "dosage",
        "treatment",
        "prescription",
        "clinical_decision",
    }
)

FORBIDDEN_KEYS = frozenset(
    {
        "diagnosis",
        "diagnose",
        "arrhythmia",
        "disease",
        "emergency",
        "medication",
        "dosage",
        "dose",
        "treatment",
        "prescription",
        "clinical_decision",
    }
)

FORBIDDEN_USER_TEXT_PATTERNS = (
    re.compile(r"\barrhythmia\b", re.I),
    re.compile(r"\bheart disease\b", re.I),
    re.compile(r"\bemergency detected\b", re.I),
    re.compile(r"\byou have\b", re.I),
    re.compile(r"\bdiagnosed\b", re.I),
    re.compile(r"\btreatment\b", re.I),
    re.compile(r"\bmedication\b", re.I),
    re.compile(r"\bdanger\b", re.I),
)

V1_CARE_SUGGESTION_TEMPLATE = (
    "Sedi noticed an unusual heart-signal pattern. This is not a diagnosis. "
    "Please check the sensor placement and take another reading. "
    "If you feel unwell or have symptoms such as chest pain, faintness, or severe "
    "shortness of breath, contact a medical professional."
)

V1_SIGNAL_QUALITY_TEMPLATE = (
    "Sedi detected a possible signal quality issue. This is not a diagnosis. "
    "Please check the sensor placement and try another reading."
)

V1_LOW_CONFIDENCE_TEMPLATE = (
    "Sedi has low confidence in this heart-signal reading. This is not a diagnosis. "
    "Please recheck the sensor and take another reading when comfortable."
)


class MlSafetyError(ValueError):
    """Raised when ML output fails V1 safety validation."""


def _contains_forbidden_key(key: str) -> bool:
    key_lower = str(key).lower()
    if key_lower in FORBIDDEN_KEYS:
        return True
    return any(fk in key_lower for fk in FORBIDDEN_KEYS)


def validate_output_type(output_type: str) -> str:
    normalized = (output_type or "").strip().lower()
    if not normalized:
        raise MlSafetyError("output_type is required")
    if normalized in FORBIDDEN_OUTPUT_TYPES:
        raise MlSafetyError(f"forbidden clinical output_type: {output_type}")
    if normalized not in ALLOWED_OUTPUT_TYPES:
        raise MlSafetyError(
            f"unsupported output_type '{output_type}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_OUTPUT_TYPES))}"
        )
    return normalized


def validate_model_status(status: str) -> str:
    normalized = (status or "research").strip().lower()
    if normalized not in ALLOWED_MODEL_STATUSES:
        raise MlSafetyError(
            f"invalid model status '{status}'. Allowed: {', '.join(sorted(ALLOWED_MODEL_STATUSES))}"
        )
    return normalized


def validate_json_payload(payload: Optional[Mapping[str, Any]], *, context: str) -> None:
    if payload is None:
        return
    for key in payload:
        if _contains_forbidden_key(str(key)):
            raise MlSafetyError(f"forbidden clinical key in {context}: {key}")
        value = payload[key]
        if isinstance(value, str) and contains_forbidden_user_text(value):
            raise MlSafetyError(f"forbidden clinical wording in {context}.{key}")
        if isinstance(value, Mapping):
            validate_json_payload(value, context=f"{context}.{key}")


def contains_forbidden_user_text(text: str) -> bool:
    if not text:
        return False
    for pattern in FORBIDDEN_USER_TEXT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def validate_user_facing_text(text: str) -> str:
    """Validate V1 care suggestion copy — must not contain clinical claims."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise MlSafetyError("user-facing text must not be empty")
    if contains_forbidden_user_text(cleaned):
        raise MlSafetyError("user-facing text contains forbidden clinical wording")
    if "not a diagnosis" not in cleaned.lower() and "not a medical diagnosis" not in cleaned.lower():
        raise MlSafetyError("user-facing text must include a 'not a diagnosis' disclaimer")
    return cleaned


def build_v1_care_suggestion_text(output_type: str) -> str:
    """Generate safe V1 care wording from internal output_type."""
    normalized = validate_output_type(output_type)
    if normalized == "signal_quality_issue":
        return V1_SIGNAL_QUALITY_TEMPLATE
    if normalized in ("low_confidence", "insufficient_data"):
        return V1_LOW_CONFIDENCE_TEMPLATE
    return V1_CARE_SUGGESTION_TEMPLATE


def validate_inference_record_fields(
    *,
    output_type: str,
    raw_output_json: Optional[Mapping[str, Any]] = None,
    features_summary_json: Optional[Mapping[str, Any]] = None,
    user_visible: bool = False,
) -> str:
    normalized_type = validate_output_type(output_type)
    validate_json_payload(raw_output_json, context="raw_output_json")
    validate_json_payload(features_summary_json, context="features_summary_json")
    if user_visible:
        raise MlSafetyError("user_visible must remain false in Gate 5-E/F/G")
    return normalized_type


def sanitize_response_record(record: Mapping[str, Any], *, exclude_keys: Sequence[str] = ()) -> dict[str, Any]:
    """Strip sensitive fields from API responses."""
    skip = frozenset(exclude_keys) | frozenset({"raw_output_json"})
    return {k: v for k, v in record.items() if k not in skip}
