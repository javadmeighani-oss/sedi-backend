"""Canonical proactive evaluation identity (PD-I8-04A frozen trigger families)."""

from __future__ import annotations

import hashlib
from datetime import date

from backend.app.services.i8.constants import TRIGGER_FAMILIES


def _hash_identity(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def build_evaluation_identity_key(
    *,
    trigger_family: str,
    user_id: int,
    source_owner: str | None = None,
    source_ref: str | None = None,
    schedule_rule_id: str | None = None,
    user_local_date: date | None = None,
    signal_type: str | None = None,
    signal_occurrence_id: str | None = None,
) -> str:
    """Deterministic evaluation identity from frozen trigger family components."""
    family = (trigger_family or "").strip().casefold()
    if family not in TRIGGER_FAMILIES:
        raise ValueError("UNSUPPORTED_TRIGGER_FAMILY")

    if family == "event":
        if not source_owner or not source_ref:
            raise ValueError("EVENT_IDENTITY_INCOMPLETE")
        return _hash_identity("event", str(user_id), source_owner.strip(), source_ref.strip())

    if family == "schedule":
        if not schedule_rule_id or user_local_date is None:
            raise ValueError("SCHEDULE_IDENTITY_INCOMPLETE")
        return _hash_identity(
            "schedule",
            str(user_id),
            schedule_rule_id.strip(),
            user_local_date.isoformat(),
        )

    # future_i9
    if not signal_type or not signal_occurrence_id:
        raise ValueError("FUTURE_I9_IDENTITY_INCOMPLETE")
    return _hash_identity(
        "future_i9",
        str(user_id),
        signal_type.strip(),
        signal_occurrence_id.strip(),
    )
