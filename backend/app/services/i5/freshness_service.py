"""I5-IMPL-W2-P02 — pure freshness-state calculator (no DB).

Fail-closed: never invent CURRENT from empty date inputs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.app.services.i5.enums import FreshnessState


class FreshnessServiceError(ValueError):
    """Fail-closed validation error for freshness helpers."""


def calculate_freshness_state(
    *,
    now: datetime,
    published_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    retrieved_at: Optional[datetime] = None,
    reviewed_at: Optional[datetime] = None,
    valid_until: Optional[datetime] = None,
    policy_days: Optional[float] = None,
) -> FreshnessState:
    """Deterministic freshness classification from date anchors and optional policy."""
    if now is None:
        raise FreshnessServiceError("FRESHNESS_NOW_REQUIRED")

    if valid_until is not None and now > valid_until:
        return FreshnessState.EXPIRED

    candidates = (published_at, updated_at, retrieved_at, reviewed_at)
    if all(value is None for value in candidates):
        return FreshnessState.UNKNOWN

    anchor = max(value for value in candidates if value is not None)

    if policy_days is None:
        if reviewed_at is not None or updated_at is not None:
            return FreshnessState.CURRENT
        return FreshnessState.UNKNOWN

    age_days = (now - anchor).total_seconds() / 86400.0
    if age_days > (2.0 * float(policy_days)):
        return FreshnessState.EXPIRED
    if age_days > float(policy_days):
        return FreshnessState.STALE
    return FreshnessState.CURRENT
