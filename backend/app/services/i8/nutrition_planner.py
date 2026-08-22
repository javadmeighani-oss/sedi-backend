"""I8 nutrition domain adapter — legacy ephemeral path delegates to unified core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK
from backend.app.services.i6.consent_service import PERM_READ, ConsentDenied, has_permission
from backend.app.services.i6.memory_writes import list_facts
from backend.app.services.i8.constants import THERAPEUTIC_TOKENS, UNSAFE_DIAGNOSIS_TOKENS
from backend.app.services.i8.unified_core import generate_operational_action


def _is_unsafe(request: str) -> bool:
    text = (request or "").casefold()
    return any(tok in text for tok in UNSAFE_DIAGNOSIS_TOKENS + THERAPEUTIC_TOKENS)


@dataclass(frozen=True)
class NutritionPlanResult:
    status: str
    iran_first: bool
    grounded: bool
    eligible_knowledge_count: int
    message: str
    plan: Optional[dict[str, Any]] = None


def _readiness_keys(facts) -> set[str]:
    return {f"{f.domain}.{f.key}" for f in facts}


def plan_nutrition(
    db: Session,
    user_id: int,
    request: str,
    *,
    iran_first: bool = True,
) -> NutritionPlanResult:
    """Legacy nutrition entrypoint — unified core, ephemeral only (no persistence)."""
    if _is_unsafe(request):
        return NutritionPlanResult(
            status="UNSAFE_REQUEST_BLOCKED",
            iran_first=iran_first,
            grounded=False,
            eligible_knowledge_count=0,
            message="Sedi will not diagnose, replace a physician, or modify medication.",
        )
    if db is None or not has_permission(db, user_id, PERM_READ):
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

    result = generate_operational_action(
        db,
        user_id=user_id,
        actor_user_id=user_id,
        request=request,
        domain="nutrition",
        persist=False,
    )
    status = result.status
    if status == "MISSING_ELIGIBLE_KNOWLEDGE":
        status = "STALE_OR_INELIGIBLE_KNOWLEDGE"
    if status == "UNSUPPORTED_CLINICAL_APPLICABILITY":
        status = "STALE_OR_INELIGIBLE_KNOWLEDGE"
    grounded = status in {"GROUNDED_EPHEMERAL", "ACTION_PERSISTED", "ACTION_READY"}
    if status == "ACTION_READY":
        status = "GROUNDED_EPHEMERAL"
    return NutritionPlanResult(
        status=status,
        iran_first=iran_first,
        grounded=grounded,
        eligible_knowledge_count=len(result.knowledge_refs),
        message=result.summary or result.rationale or status,
        plan={
            "domain": result.domain,
            "persistence": "NONE",
            "clinical": False,
            "suggestions": [{"label": s.label, "detail": s.detail} for s in result.suggestions],
        }
        if grounded
        else None,
    )
