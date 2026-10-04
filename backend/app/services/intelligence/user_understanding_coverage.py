"""CR-04F.1 — Request-local user-understanding coverage (pure, nonpersistent).

Derives KNOWN/MISSING/STALE/CONFLICTED/DENIED/NOT_APPLICABLE from an
I2 ContextSnapshot only. No DB, network, LLM, or writes.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence

from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextSnapshot,
)


class CoverageState(str, Enum):
    KNOWN = "KNOWN"
    MISSING = "MISSING"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    DENIED = "DENIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# Progressive low-risk I6 targets (CR-04F.1 Tier A).
TIER_A_TARGETS: tuple[str, ...] = (
    "preferences.interests",
    "preferences.communication_style",
    "preferences.listen_before_advice",
    "preferences.response_length",
)

# GENERAL soft-discovery order (lower index = higher priority).
TIER_A_GENERAL_PRIORITY: tuple[str, ...] = (
    "preferences.interests",
    "preferences.communication_style",
    "preferences.listen_before_advice",
    "preferences.response_length",
)

# Never missing-driven (Tier C) — coverage may still report state if present.
TIER_C_NEVER_MISSING_DRIVEN: frozenset[str] = frozenset(
    {
        "social.household_context",
        "social.support_network",
        "social.important_relationships",
        "social.social_activity_preference",
        "values.important_values",
        "values.life_priorities",
        "barriers.financial_constraints",
        "barriers.motivation_barriers",
    }
)

# Keys this helper may evaluate; others → NOT_APPLICABLE.
REGISTERED_TARGETS: frozenset[str] = frozenset(
    {
        *TIER_A_TARGETS,
        "routines.bedtime",
        "routines.wake_time",
        "lifestyle.sleep_quality",
        "lifestyle.food_habits",
        "lifestyle.activity_level",
        "routines.exercise_schedule",
        "work.work_schedule",
        "work.occupation",
        "barriers.time_constraints",
        *TIER_C_NEVER_MISSING_DRIVEN,
    }
)


def _items_for_key(
    items: Sequence[ContextItem], target_key: str
) -> list[ContextItem]:
    return [i for i in items if i.canonical_key == target_key]


def coverage_state_for_key(
    snapshot: ContextSnapshot, target_key: str
) -> CoverageState:
    """Derive coverage for one registered key from snapshot items only."""
    if target_key not in REGISTERED_TARGETS:
        return CoverageState.NOT_APPLICABLE

    matched = _items_for_key(snapshot.items, target_key)
    if not matched:
        return CoverageState.MISSING

    # Prefer decisive negative states over presence.
    if any(i.consent == "denied" for i in matched):
        return CoverageState.DENIED
    if any(i.conflicted for i in matched):
        return CoverageState.CONFLICTED
    # Do not fabricate freshness — only honor explicit stale stamps.
    if any(getattr(i, "freshness", None) == "stale" for i in matched):
        return CoverageState.STALE
    if any(i.active for i in matched):
        return CoverageState.KNOWN
    # Inactive non-conflicted/denied/stale items do not count as known.
    return CoverageState.MISSING


def is_safe_missing_for_discovery(
    snapshot: ContextSnapshot, target_key: str
) -> bool:
    """True only when coverage is MISSING and key is not Tier-C restricted."""
    if target_key in TIER_C_NEVER_MISSING_DRIVEN:
        return False
    return coverage_state_for_key(snapshot, target_key) is CoverageState.MISSING


def first_missing_tier_a(
    snapshot: ContextSnapshot,
    *,
    priority: Sequence[str] = TIER_A_GENERAL_PRIORITY,
) -> Optional[str]:
    """Return the first MISSING Tier-A key in priority order, else None."""
    for key in priority:
        if key not in TIER_A_TARGETS:
            continue
        if is_safe_missing_for_discovery(snapshot, key):
            return key
    return None
