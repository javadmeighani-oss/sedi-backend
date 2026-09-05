"""Unified I8 reactive operational action core (PD-I8-03)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.services.i6.consent_service import PERM_READ, ConsentDenied, has_permission
from backend.app import models
from backend.app.services.i8.constants import (
    ACTION_DOMAINS,
    PRESENTATION_JSON_MAX_BYTES,
    REPLAYABLE_ACTION_STATUSES,
    REPLAYABLE_PLAN_STATUSES,
    SUMMARY_TEXT_MAX_LEN,
)
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.contracts import I8ActionSuggestion, I8OperationalActionResult
from backend.app.services.i8.knowledge_bridge import (
    build_persisted_operational_snapshot,
    compose_grounded_action,
    knowledge_refs_payload,
    retrieve_governed_knowledge,
)
from backend.app.services.i8.lifecycle import I8OperationalLifecycle
from backend.app.services.i8.local_day import (
    I8InvalidTimezoneError,
    I8TimezoneRequiredError,
    local_day_utc_span_seconds,
    resolve_local_day_window,
)
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.safety import evaluate_composed_safety, evaluate_safety


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


def _validate_presentation(payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > PRESENTATION_JSON_MAX_BYTES:
        raise ValueError("PRESENTATION_JSON_TOO_LARGE")


def _idempotency_key(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _candidate_text(suggestions) -> str:
    return " ".join(f"{s.label} {s.detail}" for s in suggestions)


def _replay_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_knowledge_refs_json(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


def _replay_ineligibility_reason(
    *,
    plan: models.I8OperationalPlan,
    action: models.I8OperationalPlanAction,
    now_utc: datetime | None = None,
) -> str | None:
    if plan.user_id != action.user_id:
        return "ownership_mismatch"
    if plan.status not in REPLAYABLE_PLAN_STATUSES:
        return f"plan_status_{plan.status}"
    if action.status not in REPLAYABLE_ACTION_STATUSES:
        return f"action_status_{action.status}"
    now = _as_utc(now_utc or _replay_now_utc())
    for boundary in (plan.valid_until, action.valid_until):
        if boundary is not None and now > _as_utc(boundary):
            return "past_valid_until"
    return None


def _build_replay_not_eligible_result(
    *,
    plan: models.I8OperationalPlan,
    action: models.I8OperationalPlanAction,
    generation_mode: str,
    refs: list[dict],
    reason: str,
) -> I8OperationalActionResult:
    return I8OperationalActionResult(
        status="ACTION_NOT_REPLAYABLE",
        domain=action.action_domain,
        action_mode=generation_mode,
        safety_state=action.safety_state,
        clarification_required=True,
        summary=f"Persisted operational action is not replayable ({reason}).",
        knowledge_refs=refs,
        valid_from=action.valid_from.isoformat() if action.valid_from else None,
        valid_until=action.valid_until.isoformat() if action.valid_until else None,
        plan_id=int(plan.id),
        action_id=int(action.id),
        persisted=True,
    )


def _build_replay_result(
    *,
    plan: models.I8OperationalPlan,
    action: models.I8OperationalPlanAction,
    generation_mode: str,
    now_utc: datetime | None = None,
) -> I8OperationalActionResult:
    refs = _parse_knowledge_refs_json(action.knowledge_refs_json)
    if not refs:
        return I8OperationalActionResult(
            status="ACTION_PROVENANCE_INTEGRITY",
            domain=action.action_domain,
            action_mode=generation_mode,
            safety_state="CLARIFY",
            clarification_required=True,
            summary="Persisted knowledge references are unavailable for replay.",
            plan_id=int(plan.id),
            action_id=int(action.id),
            persisted=True,
        )
    ineligible = _replay_ineligibility_reason(plan=plan, action=action, now_utc=now_utc)
    if ineligible is not None:
        return _build_replay_not_eligible_result(
            plan=plan,
            action=action,
            generation_mode=generation_mode,
            refs=refs,
            reason=ineligible,
        )
    summary = action.summary_text
    return I8OperationalActionResult(
        status="ACTION_PERSISTED",
        domain=action.action_domain,
        action_mode=generation_mode,
        summary=summary,
        suggestions=[
            I8ActionSuggestion(
                label=summary,
                detail="Persisted operational action reference.",
            )
        ],
        rationale="Idempotent replay from persisted operational state.",
        safety_state=action.safety_state,
        clarification_required=bool(action.clarification_required),
        knowledge_refs=refs,
        valid_from=action.valid_from.isoformat() if action.valid_from else None,
        valid_until=action.valid_until.isoformat() if action.valid_until else None,
        plan_id=int(plan.id),
        action_id=int(action.id),
        persisted=True,
    )


def _try_idempotent_replay(
    db: Session,
    *,
    user_id: int,
    generation_mode: str,
    plan_idempotency_key: str,
    action_idempotency_key: str,
) -> I8OperationalActionResult | None:
    repo = I8OperationalRepository()
    plan, action = repo.get_idempotent_replay(
        db,
        user_id=user_id,
        plan_idempotency_key=plan_idempotency_key,
        action_idempotency_key=action_idempotency_key,
    )
    if action is None:
        return None
    return _build_replay_result(plan=plan, action=action, generation_mode=generation_mode)


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
    proactive_evaluation_key: Optional[str] = None,
    health_subject_id: Optional[int] = None,
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

    if persist:
        try:
            window = resolve_local_day_window(db, user_id)
        except I8TimezoneRequiredError:
            return I8OperationalActionResult(
                status="TIMEZONE_REQUIRED",
                domain=resolved_domain,
                safety_state="CLARIFY",
                clarification_required=True,
                summary="UserProfileCore.timezone is required for I8 operational plans.",
            )
        except I8InvalidTimezoneError:
            return I8OperationalActionResult(
                status="TIMEZONE_INVALID",
                domain=resolved_domain,
                safety_state="CLARIFY",
                clarification_required=True,
                summary="UserProfileCore.timezone must be a valid IANA timezone.",
            )

        plan_key = plan_idempotency_key or _idempotency_key(
            str(user_id), window.user_local_date.isoformat(), generation_mode, resolved_domain
        )
        action_key = action_idempotency_key or _idempotency_key(
            plan_key, request.strip().casefold()
        )
        replay = _try_idempotent_replay(
            db,
            user_id=user_id,
            generation_mode=generation_mode,
            plan_idempotency_key=plan_key,
            action_idempotency_key=action_key,
        )
        if replay is not None:
            return replay
    else:
        window = None
        plan_key = None
        action_key = None

    # Subject-aware path: actor Account remains gateway; patient = health_subject_id.
    if health_subject_id is not None:
        from backend.app.services.i8.subject_context import (
            load_subject_trusted_context,
            to_i8_trusted_context_compat,
        )
        from backend.app.services.i9.health_subject_service import HealthSubjectAccessDenied

        try:
            subject_ctx = load_subject_trusted_context(
                db,
                actor_account_user_id=actor_user_id,
                health_subject_id=health_subject_id,
            )
        except HealthSubjectAccessDenied:
            return I8OperationalActionResult(
                status="SUBJECT_ACCESS_DENIED",
                domain=resolved_domain,
                safety_state="BLOCKED",
                clarification_required=True,
                summary="Actor Account is not authorized for the target HealthSubject.",
            )
        ctx = to_i8_trusted_context_compat(subject_ctx)
    else:
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
    retrieval_safety = evaluate_safety(
        request=request, ctx=ctx, retrieval=retrieval, domain=resolved_domain
    )
    if not retrieval_safety.allowed:
        return I8OperationalActionResult(
            status=retrieval_safety.status,
            domain=resolved_domain,
            safety_state=retrieval_safety.safety_state,
            clarification_required=retrieval_safety.clarification_required,
            summary=retrieval_safety.message,
        )

    composition = compose_grounded_action(retrieval, domain=resolved_domain, ctx=ctx)
    if composition is None:
        return I8OperationalActionResult(
            status="MISSING_GROUNDED_ACTION_CONTENT",
            domain=resolved_domain,
            safety_state="CLARIFY",
            clarification_required=True,
            summary="No usable grounded action could be formed from governed knowledge.",
        )

    suggestions = composition.suggestions
    candidate = _candidate_text(suggestions)
    post_safety = evaluate_composed_safety(candidate_text=candidate, ctx=ctx)
    if not post_safety.allowed:
        return I8OperationalActionResult(
            status=post_safety.status,
            domain=resolved_domain,
            safety_state=post_safety.safety_state,
            clarification_required=post_safety.clarification_required,
            summary=post_safety.message,
        )

    summary = suggestions[0].detail[:SUMMARY_TEXT_MAX_LEN]
    refs = json.loads(knowledge_refs_payload(composition.used_items))
    request_fingerprint = _idempotency_key(request.strip().casefold())[:16]
    response_presentation = {
        "domain": resolved_domain,
        "action_type": _default_action_type(resolved_domain),
        "rationale": composition.rationale,
        "suggestions": [{"label": s.label, "detail": s.detail} for s in suggestions],
        "request_fingerprint": request_fingerprint,
        "grounded_knowledge_unit_ids": [r["knowledge_unit_id"] for r in refs],
    }
    try:
        _validate_presentation(response_presentation)
    except ValueError:
        return I8OperationalActionResult(
            status="PRESENTATION_TOO_LARGE",
            domain=resolved_domain,
            safety_state="BLOCKED",
            summary="Presentation payload exceeds allowed bound.",
        )

    persisted_summary, persisted_presentation = build_persisted_operational_snapshot(
        domain=resolved_domain,
        action_type=_default_action_type(resolved_domain),
        used_items=composition.used_items,
        request_fingerprint=request_fingerprint,
        safety_state="SAFE",
    )
    try:
        _validate_presentation(persisted_presentation)
    except ValueError:
        return I8OperationalActionResult(
            status="PRESENTATION_TOO_LARGE",
            domain=resolved_domain,
            safety_state="BLOCKED",
            summary="Persisted presentation payload exceeds allowed bound.",
        )

    try:
        if window is None:
            window = resolve_local_day_window(db, user_id)
    except I8TimezoneRequiredError:
        return I8OperationalActionResult(
            status="TIMEZONE_REQUIRED",
            domain=resolved_domain,
            safety_state="CLARIFY",
            clarification_required=True,
            summary="UserProfileCore.timezone is required for I8 operational plans.",
        )
    except I8InvalidTimezoneError:
        return I8OperationalActionResult(
            status="TIMEZONE_INVALID",
            domain=resolved_domain,
            safety_state="CLARIFY",
            clarification_required=True,
            summary="UserProfileCore.timezone must be a valid IANA timezone.",
        )

    trace_id = str(uuid.uuid4())
    result = I8OperationalActionResult(
        status="ACTION_READY",
        domain=resolved_domain,
        action_mode=generation_mode,
        summary=summary,
        suggestions=suggestions,
        rationale=composition.rationale,
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
    if plan_key is None:
        plan_key = plan_idempotency_key or _idempotency_key(
            str(user_id), window.user_local_date.isoformat(), generation_mode, resolved_domain
        )
    if action_key is None:
        action_key = action_idempotency_key or _idempotency_key(plan_key, request.strip().casefold())

    try:
        plan, _ = lifecycle.ensure_active_plan(
            db,
            user_id=user_id,
            window=window,
            generation_mode=generation_mode,
            plan_idempotency_key=plan_key,
            trace_id=trace_id,
            proactive_evaluation_key=proactive_evaluation_key,
        )
        action, _ = lifecycle.ensure_action(
            db,
            user_id=user_id,
            plan=plan,
            window=window,
            action_domain=resolved_domain,
            action_type=_default_action_type(resolved_domain),
            action_idempotency_key=action_key,
            summary_text=persisted_summary,
            presentation_json=json.dumps(persisted_presentation, ensure_ascii=False, separators=(",", ":")),
            knowledge_refs_json=knowledge_refs_payload(composition.used_items),
            safety_state="SAFE",
            context_refs_json=json.dumps(ctx.context_refs[:8]),
            trace_id=trace_id,
            proactive_evaluation_key=proactive_evaluation_key,
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
