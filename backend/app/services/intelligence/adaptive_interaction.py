"""CR-04D — Pure adaptive interaction preference resolver.

Request-local only. No DB, network, LLM, or writes.
Accepts confirmed I6 interaction preferences from an I2 ContextSnapshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Optional

from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextSnapshot,
    is_llm_projection_eligible,
)

ResponseLengthPref = Literal["brief", "detailed"]

SUPPORTED_RESPONSE_LENGTH_KEY = "preferences.response_length"
SUPPORTED_LISTEN_BEFORE_ADVICE_KEY = "preferences.listen_before_advice"

_ACCEPTED_EPISTEMIC = frozenset({"USER_STATED", "USER_CONFIRMED"})

REASON_RESPONSE_LENGTH_BRIEF = "I6_PREF_RESPONSE_LENGTH_BRIEF"
REASON_RESPONSE_LENGTH_DETAILED = "I6_PREF_RESPONSE_LENGTH_DETAILED"
REASON_LISTEN_BEFORE_ADVICE = "I6_PREF_LISTEN_BEFORE_ADVICE"


@dataclass(frozen=True)
class AdaptiveInteractionResult:
    """Bounded adaptive directives for the single generator call."""

    response_length: Optional[ResponseLengthPref] = None
    listen_before_advice: bool = False
    reason_codes: tuple[str, ...] = ()


def _coerce_structured_value(raw: Any) -> Any:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return text
    return raw


def _is_canonical_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().casefold() == "true":
        return True
    return False


def _item_preference_eligible(item: ContextItem) -> bool:
    if not item.active or item.conflicted:
        return False
    if not is_llm_projection_eligible(item):
        return False
    if item.sensitivity in ("high", "critical"):
        return False
    epistemic = (item.epistemic_class or "").strip()
    if epistemic not in _ACCEPTED_EPISTEMIC:
        return False
    return True


def _find_supported_item(
    snapshot: ContextSnapshot, canonical_key: str
) -> Optional[ContextItem]:
    for item in snapshot.items:
        if item.canonical_key == canonical_key and _item_preference_eligible(item):
            return item
    return None


def resolve_adaptive_interaction(
    snapshot: ContextSnapshot,
) -> AdaptiveInteractionResult:
    """Resolve bounded adaptive directives from an assembled ContextSnapshot."""
    response_length: Optional[ResponseLengthPref] = None
    listen_before_advice = False
    codes: list[str] = []

    length_item = _find_supported_item(snapshot, SUPPORTED_RESPONSE_LENGTH_KEY)
    if length_item is not None:
        coerced = _coerce_structured_value(length_item.structured_value)
        if isinstance(coerced, str):
            normalized = coerced.strip().casefold()
            if normalized in ("brief", "detailed"):
                response_length = normalized  # type: ignore[assignment]
                codes.append(
                    REASON_RESPONSE_LENGTH_BRIEF
                    if normalized == "brief"
                    else REASON_RESPONSE_LENGTH_DETAILED
                )

    listen_item = _find_supported_item(snapshot, SUPPORTED_LISTEN_BEFORE_ADVICE_KEY)
    if listen_item is not None:
        coerced = _coerce_structured_value(listen_item.structured_value)
        if _is_canonical_true(coerced):
            listen_before_advice = True
            codes.append(REASON_LISTEN_BEFORE_ADVICE)

    return AdaptiveInteractionResult(
        response_length=response_length,
        listen_before_advice=listen_before_advice,
        reason_codes=tuple(codes),
    )
