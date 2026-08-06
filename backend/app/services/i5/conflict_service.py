"""I5-IMPL-W2-P02 — pure conflict detection / transition helpers (no DB)."""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Tuple, Union

from backend.app.services.i5.enums import ConflictState

_FIELD_SEP = "\x1f"

_COMPARE_FIELDS: tuple[str, ...] = (
    "normalized_statement",
    "applicability",
    "exclusions",
    "medical_safety_state",
    "evidence_strength",
)

_ALLOWED_CONFLICT_TRANSITIONS: frozenset[tuple[ConflictState, ConflictState]] = frozenset(
    {
        (ConflictState.NONE, ConflictState.NONE),
        (ConflictState.NONE, ConflictState.SUSPECTED),
        (ConflictState.SUSPECTED, ConflictState.SUSPECTED),
        (ConflictState.SUSPECTED, ConflictState.CONFIRMED),
        (ConflictState.SUSPECTED, ConflictState.RESOLVED),
        (ConflictState.CONFIRMED, ConflictState.CONFIRMED),
        (ConflictState.CONFIRMED, ConflictState.RESOLVED),
        (ConflictState.RESOLVED, ConflictState.RESOLVED),
    }
)


class ConflictServiceError(ValueError):
    """Fail-closed validation error for conflict helpers."""


def _as_mapping(obj: Union[Mapping[str, Any], Any]) -> Mapping[str, Any]:
    if isinstance(obj, Mapping):
        return obj
    keys = _COMPARE_FIELDS + (
        "domain",
        "topic_taxonomy",
        "topic",
        "provenance_complete",
    )
    return {key: getattr(obj, key, None) for key in keys}


def _norm(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def _topic_of(data: Mapping[str, Any]) -> Any:
    topic = data.get("topic_taxonomy")
    if topic is None:
        topic = data.get("topic")
    return _norm(topic)


def order_unit_ids(a: int, b: int) -> Tuple[int, int]:
    """Return canonical (min, max) knowledge-unit id pair."""
    if a is None or b is None:
        raise ConflictServiceError("UNIT_IDS_REQUIRED")
    left = int(a)
    right = int(b)
    if left == right:
        raise ConflictServiceError("UNIT_IDS_MUST_DIFFER")
    return (left, right) if left < right else (right, left)


def build_conflict_idempotency_key(a: int, b: int, summary_hash: str) -> str:
    """SHA-256 hex of ordered unit ids + summary hash."""
    left, right = order_unit_ids(a, b)
    digest = (summary_hash or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ConflictServiceError("SUMMARY_HASH_INVALID")
    payload = f"{left}{_FIELD_SEP}{right}{_FIELD_SEP}{digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_conflict_key(a: int, b: int) -> str:
    """Logical conflict identity key for an ordered unit pair (SHA-256 hex)."""
    left, right = order_unit_ids(a, b)
    payload = f"kc{_FIELD_SEP}{left}{_FIELD_SEP}{right}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_structured_conflict(
    ku_a: Union[Mapping[str, Any], Any],
    ku_b: Union[Mapping[str, Any], Any],
) -> ConflictState:
    """Compare two KU snapshots; return NONE / SUSPECTED / CONFIRMED."""
    left = _as_mapping(ku_a)
    right = _as_mapping(ku_b)

    left_vals = tuple(_norm(left.get(field)) for field in _COMPARE_FIELDS)
    right_vals = tuple(_norm(right.get(field)) for field in _COMPARE_FIELDS)
    if left_vals == right_vals:
        return ConflictState.NONE

    same_domain = _norm(left.get("domain")) == _norm(right.get("domain"))
    same_topic = _topic_of(left) == _topic_of(right) and _topic_of(left) is not None
    if not (same_domain and same_topic):
        return ConflictState.NONE

    stmt_differs = _norm(left.get("normalized_statement")) != _norm(
        right.get("normalized_statement")
    )
    safety_differs = _norm(left.get("medical_safety_state")) != _norm(
        right.get("medical_safety_state")
    )
    if not (stmt_differs or safety_differs):
        # Same domain/topic but other compared fields differ (evidence/applicability/exclusions).
        return ConflictState.SUSPECTED

    both_complete = bool(left.get("provenance_complete")) and bool(
        right.get("provenance_complete")
    )
    if both_complete and stmt_differs:
        return ConflictState.CONFIRMED
    return ConflictState.SUSPECTED


def _coerce_conflict_state(value: Union[str, ConflictState]) -> ConflictState:
    if isinstance(value, ConflictState):
        return value
    try:
        return ConflictState(str(value))
    except ValueError as exc:
        raise ConflictServiceError(f"CONFLICT_STATE_INVALID:{value}") from exc


def assert_allowed_conflict_transition(
    old: Union[str, ConflictState],
    new: Union[str, ConflictState],
) -> None:
    """Fail-closed conflict-state transition guard."""
    old_state = _coerce_conflict_state(old)
    new_state = _coerce_conflict_state(new)
    if (old_state, new_state) not in _ALLOWED_CONFLICT_TRANSITIONS:
        raise ConflictServiceError(
            f"ILLEGAL_CONFLICT_TRANSITION:{old_state.value}->{new_state.value}"
        )
