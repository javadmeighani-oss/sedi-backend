"""Numeric / structural validation for KNOW-03 effect estimates."""

from __future__ import annotations

import math
from typing import Optional


class EffectValidationError(ValueError):
    pass


def _reject_nonfinite(name: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise EffectValidationError(f"INVALID_NUMERIC:{name}")
    try:
        f = float(value)
    except (TypeError, ValueError) as e:
        raise EffectValidationError(f"INVALID_NUMERIC:{name}") from e
    if math.isnan(f) or math.isinf(f):
        raise EffectValidationError(f"NONFINITE_NUMERIC:{name}")
    return f


def validate_effect_payload(
    *,
    effect_value: Optional[float] = None,
    ci_lower: Optional[float] = None,
    ci_upper: Optional[float] = None,
    confidence_level: Optional[float] = None,
    p_value: Optional[float] = None,
    sample_size_analyzed: Optional[int] = None,
    event_count_intervention: Optional[int] = None,
    event_count_comparator: Optional[int] = None,
) -> dict:
    effect_value = _reject_nonfinite("effect_value", effect_value)
    ci_lower = _reject_nonfinite("ci_lower", ci_lower)
    ci_upper = _reject_nonfinite("ci_upper", ci_upper)
    confidence_level = _reject_nonfinite("confidence_level", confidence_level)
    p_value = _reject_nonfinite("p_value", p_value)

    if ci_lower is not None and ci_upper is not None and ci_lower > ci_upper:
        raise EffectValidationError("CI_LOWER_GT_UPPER")
    if confidence_level is not None and not (0 < confidence_level < 100):
        raise EffectValidationError("CONFIDENCE_LEVEL_OUT_OF_DOMAIN")
    if sample_size_analyzed is not None and sample_size_analyzed < 0:
        raise EffectValidationError("NEGATIVE_SAMPLE_SIZE")
    if event_count_intervention is not None and event_count_intervention < 0:
        raise EffectValidationError("NEGATIVE_EVENT_COUNT")
    if event_count_comparator is not None and event_count_comparator < 0:
        raise EffectValidationError("NEGATIVE_EVENT_COUNT")
    if (
        sample_size_analyzed is not None
        and event_count_intervention is not None
        and event_count_intervention > sample_size_analyzed
    ):
        raise EffectValidationError("EVENT_COUNT_GT_SAMPLE_SIZE")
    if (
        sample_size_analyzed is not None
        and event_count_comparator is not None
        and event_count_comparator > sample_size_analyzed
    ):
        raise EffectValidationError("EVENT_COUNT_GT_SAMPLE_SIZE")

    return {
        "effect_value": effect_value,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "confidence_level": confidence_level,
        "p_value": p_value,
        "sample_size_analyzed": sample_size_analyzed,
        "event_count_intervention": event_count_intervention,
        "event_count_comparator": event_count_comparator,
    }
