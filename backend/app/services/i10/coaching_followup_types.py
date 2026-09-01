"""I10-B13 coaching follow-up vocabulary — I8 operational plan action authority."""

from __future__ import annotations

from enum import Enum

LIFESTYLE_DOMAINS = frozenset({"routine", "lifestyle", "wellbeing"})
NUTRITION_DOMAINS = frozenset({"nutrition"})
EXERCISE_DOMAINS = frozenset({"exercise"})


class CoachingPlanDomain(str, Enum):
    LIFESTYLE = "lifestyle"
    NUTRITION = "nutrition"
    EXERCISE = "exercise"


def resolve_coaching_domain(action_domain: str) -> CoachingPlanDomain | None:
    domain = (action_domain or "").strip().lower()
    if domain in NUTRITION_DOMAINS:
        return CoachingPlanDomain.NUTRITION
    if domain in EXERCISE_DOMAINS:
        return CoachingPlanDomain.EXERCISE
    if domain in LIFESTYLE_DOMAINS:
        return CoachingPlanDomain.LIFESTYLE
    return None
