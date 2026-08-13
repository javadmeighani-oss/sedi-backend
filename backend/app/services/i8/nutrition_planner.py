"""I8 nutrition planning — ephemeral, fail-closed, no new tables, no diagnosis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i5.runtime_knowledge_retrieval import (
    STATUS_OK,
    retrieve_knowledge_context,
)
from backend.app.services.i6.consent_service import PERM_READ, ConsentDenied, has_permission
from backend.app.services.i6.memory_writes import list_facts

UNSAFE_TOKENS = (
    "diagnose",
    "diagnosis",
    "prescribe",
    "prescription",
    "change my medication",
    "stop taking",
    "increase dose",
    "decrease dose",
)


@dataclass(frozen=True)
class NutritionPlanResult:
    status: str
    iran_first: bool
    grounded: bool
    eligible_knowledge_count: int
    message: str
    plan: Optional[dict[str, Any]] = None


def _is_unsafe(request: str) -> bool:
    text = (request or "").casefold()
    return any(tok in text for tok in UNSAFE_TOKENS)


def _readiness_keys(facts) -> set[str]:
    return {f"{f.domain}.{f.key}" for f in facts}


def plan_nutrition(
    db: Session,
    user_id: int,
    request: str,
    *,
    iran_first: bool = True,
) -> NutritionPlanResult:
    if _is_unsafe(request):
        return NutritionPlanResult(
            status="UNSAFE_REQUEST_BLOCKED",
            iran_first=iran_first,
            grounded=False,
            eligible_knowledge_count=0,
            message="Sedi will not diagnose, replace a physician, or modify medication.",
        )
    if not has_permission(db, user_id, PERM_READ):
        return NutritionPlanResult(
            status="CONSENT_REQUIRED",
            iran_first=iran_first,
            grounded=False,
            eligible_knowledge_count=0,
            message="Memory consent is required before personalized nutrition help.",
        )
    try:
        facts = list_facts(db, user_id)
    except ConsentDenied:
        return NutritionPlanResult(
            status="CONSENT_REQUIRED",
            iran_first=iran_first,
            grounded=False,
            eligible_knowledge_count=0,
            message="Memory consent is required before personalized nutrition help.",
        )
    keys = _readiness_keys(facts)
    needed = {"lifestyle.diet_notes", "lifestyle.food_habits", "goals.health_goals"}
    if not (keys & needed):
        return NutritionPlanResult(
            status="INSUFFICIENT_DATA",
            iran_first=iran_first,
            grounded=False,
            eligible_knowledge_count=0,
            message="Not enough confirmed lifestyle facts for a personalized meal plan.",
        )
    retrieval = retrieve_knowledge_context(db, request, enqueue_gap_on_empty=False)
    eligible = len(list(getattr(retrieval, "items", None) or []))
    status = getattr(retrieval, "status", None)
    if eligible == 0 or status != STATUS_OK:
        code = "STALE_OR_INELIGIBLE_KNOWLEDGE" if status and status != STATUS_OK else "MISSING_ELIGIBLE_KNOWLEDGE"
        return NutritionPlanResult(
            status=code,
            iran_first=iran_first,
            grounded=False,
            eligible_knowledge_count=eligible,
            message="Approved governed knowledge is unavailable; fail-closed. No personalized clinical nutrition plan.",
        )
    return NutritionPlanResult(
        status="GROUNDED_EPHEMERAL",
        iran_first=iran_first,
        grounded=True,
        eligible_knowledge_count=eligible,
        message="Ephemeral suggestion only; not stored; not a medical diet.",
        plan={
            "iran_first": iran_first,
            "persistence": "NONE",
            "clinical": False,
        },
    )
