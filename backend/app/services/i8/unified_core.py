"""Unified I8 reactive operational action core (PD-I8-03)."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.services.i6.consent_service import PERM_READ, ConsentDenied, has_permission
from backend.app.services.i8.constants import (
    ACTION_DOMAINS,
    PRESENTATION_JSON_MAX_BYTES,
    SUMMARY_TEXT_MAX_LEN,
)
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.contracts import I8ActionSuggestion, I8OperationalActionResult
from backend.app.services.i8.knowledge_bridge import knowledge_refs_payload, retrieve_governed_knowledge
from backend.app.services.i8.lifecycle import I8OperationalLifecycle
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.safety import evaluate_safety


_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "nutrition": ("meal", "food", "eat", "breakfast", "lunch", "dinner", "nutrition", "diet"),
    "exercise": ("exercise", "workout", "walk", "run", "steps", "activity"),
    "routine": ("routine", "schedule", "habit", "daily plan"),
    "lifestyle": ("sleep", "hydration", "water", "lifestyle"),
    "wellbeing": ("stress", "mood", "wellbeing", "relax"),
}


def infer_domain(request: str, explicit: Optional[str] = None) -> str:
    if explicit and explicit in ACTION_DOMAINS:
        return explicit
    text = (request or "").casefold()
    hits = [d for d, kws in _DOMAIN_KEYWORDS.items() if any(k in text for k in kws)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return "cross_domain"
    return "wellbeing"


def _default_action_type(domain: str) -> str:
    return {
        "nutrition": "meal_suggestion",
        "exercise": "activity_suggestion",
        "routine": "routine_suggestion",
        "lifestyle": "lifestyle_suggestion",
        "wellbeing": "wellbeing_suggestion",
        "cross_domain": "cross_domain_suggestion",
    }[domain]


def _compose_suggestions(domain: str, request: str, ctx) -> list[I8ActionSuggestion]:
    goal_hint = ctx.goals[0] if ctx.goals else "your health goal"
    if domain == "nutrition":
        return [I8ActionSuggestion(label="Balanced meal", detail=f"Plan a balanced meal aligned with {goal_hint}.")]
    if domain == "exercise":
        return [I8ActionSuggestion(label="Light activity", detail="Choose a moderate activity you can complete today.")]
    if domain == "routine":
        return [I8ActionSuggestion(label="Daily routine", detail="Block a consistent time for your priority routine.")]
    if domain == "cross_domain":
        return [
            I8ActionSuggestion(label="Morning routine", detail="Combine hydration, light movement, and a balanced breakfast."),
            I8ActionSuggestion(label="Goal check-in", detail=f"Review progress toward {goal_hint} this evening."),
        ]
    return [I8ActionSuggestion(label="Wellbeing step", detail="Take one small wellbeing action you can finish today.")]


def _validate_presentation(payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > PRESENTATION_JSON_MAX_BYTES:
        raise ValueError("PRESENTATION_JSON_TOO_LARGE")


def _idempotency_key(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def generate_operational_action(
    db: Session,
    *,
    user_id: int,
    actor_user_id: int,
    request: str,
    domain: Optional[str] = None,
    persist: bool = True,
    plan_idempotency_key: Optional[str] = None,
    action_idempotency_key: Optional[str] = None,
    generation_mode: str = "reactive",
) -> I8OperationalActionResult:
    if actor_user_id != user_id:
        return I8OperationalActionResult(
            status="AUTH_IDENTITY_MISMATCH",
            domain=domain or "cross_domain",
            safety_state="BLOCKED",
            clarification_required=True,
            summary="Authenticated identity mismatch.",
        )

    resolved_domain = infer_domain(request, domain)

    if not has_permission(db, user_id, PERM_READ):
        return I8OperationalActionResult(
            status="CONSENT_REQUIRED",
            domain=resolved_domain,
            safety_state="CLARIFY",
            clarification_required=True,
            summary="Memory consent is required before personalized actions.",
        )

    ctx = load_trusted_context(db, user_id)
    pre_safety = evaluate_safety(request=request, ctx=ctx, retrieval=None, domain=resolved_domain)
    if not pre_safety.allowed:
        return I8OperationalActionResult(
            status=pre_safety.status,
            domain=resolved_domain,
            safety_state=pre_safety.safety_state,
            clarification_required=pre_safety.clarification_required,
            summary=pre_safety.message,
        )

    retrieval = retrieve_governed_knowledge(
        db, user_id=user_id, query=request, domain=resolved_domain, ctx=ctx
    )
    post_safety = evaluate_safety(
        request=request, ctx=ctx, retrieval=retrieval, domain=resolved_domain
    )
    if not post_safety.allowed:
        return I8OperationalActionResult(
            status=post_safety.status,
            domain=resolved_domain,
            safety_state=post_safety.safety_state,
            clarification_required=post_safety.clarification_required,
            summary=post_safety.message,
        )

    suggestions = _compose_suggestions(resolved_domain, request, ctx)
    summary = suggestions[0].detail[:SUMMARY_TEXT_MAX_LEN]
    refs = json.loads(knowledge_refs_payload(retrieval.items))
    presentation = {
        "domain": resolved_domain,
        "action_type": _default_action_type(resolved_domain),
        "rationale": "Governed I5-grounded same-day operational suggestion.",
        "suggestions": [{"label": s.label, "detail": s.detail} for s in suggestions],
        "request_fingerprint": _idempotency_key(request.strip().casefold())[:16],
    }
    try:
        _validate_presentation(presentation)
    except ValueError:
        return I8OperationalActionResult(
            status="PRESENTATION_TOO_LARGE",
            domain=resolved_domain,
            safety_state="BLOCKED",
            summary="Presentation payload exceeds allowed bound.",
        )

    window = resolve_local_day_window(db, user_id)
    trace_id = str(uuid.uuid4())
    result = I8OperationalActionResult(
        status="ACTION_READY",
        domain=resolved_domain,
        action_mode=generation_mode,
        summary=summary,
        suggestions=suggestions,
        rationale=presentation["rationale"],
        safety_state="SAFE",
        knowledge_refs=refs,
        valid_from=window.valid_from.isoformat(),
        valid_until=window.valid_until.isoformat(),
        persisted=False,
    )

    if not persist:
        result.status = "GROUNDED_EPHEMERAL"
        return result

    lifecycle = I8OperationalLifecycle()
    plan_key = plan_idempotency_key or _idempotency_key(
        str(user_id), window.user_local_date.isoformat(), generation_mode, resolved_domain
    )
    action_key = action_idempotency_key or _idempotency_key(plan_key, request.strip().casefold())

    try:
        plan, _ = lifecycle.ensure_active_plan(
            db,
            user_id=user_id,
            window=window,
            generation_mode=generation_mode,
            plan_idempotency_key=plan_key,
            trace_id=trace_id,
        )
        action, _ = lifecycle.ensure_action(
            db,
            user_id=user_id,
            plan=plan,
            window=window,
            action_domain=resolved_domain,
            action_type=_default_action_type(resolved_domain),
            action_idempotency_key=action_key,
            summary_text=summary,
            presentation_json=json.dumps(presentation, ensure_ascii=False, separators=(",", ":")),
            knowledge_refs_json=knowledge_refs_payload(retrieval.items),
            safety_state="SAFE",
            context_refs_json=json.dumps(ctx.context_refs[:8]),
            trace_id=trace_id,
        )
        db.commit()
    except ConsentDenied:
        db.rollback()
        return I8OperationalActionResult(
            status="CONSENT_REQUIRED",
            domain=resolved_domain,
            safety_state="CLARIFY",
            clarification_required=True,
            summary="Memory consent is required before personalized actions.",
        )
    except Exception:
        db.rollback()
        raise

    result.status = "ACTION_PERSISTED"
    result.plan_id = int(plan.id)
    result.action_id = int(action.id)
    result.persisted = True
    return result
