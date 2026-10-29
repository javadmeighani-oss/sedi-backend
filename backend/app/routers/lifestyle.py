# app/routers/lifestyle.py
import os
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.services.memory import build_memory_context
from backend.app.services.lifestyle.summary_service import generate_summary
from backend.app.services.i6.consent_service import ConsentDenied
from backend.app.services.i6.memory_writes import MemoryWriteError, write_fact
from backend.app.routers.auth_otp import get_current_user


router = APIRouter()


@router.get("/health-hr", response_model=APIResponse)
def lifestyle_health_hr(
    range_key: str = Query("7d", description="7d|30d|3m|1y"),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SELF-only I9 HR status + latest value + bounded rollup history (presentation)."""
    from backend.app.services.lifestyle.a3_health_hr_projection import (
        build_lifestyle_hr_projection,
    )

    return APIResponse(
        ok=True,
        data=build_lifestyle_hr_projection(db, auth_user.id, range_key=range_key),
    )


@router.get("/schedule-actions", response_model=APIResponse)
def lifestyle_schedule_actions(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compact I8 active actions for My Schedule (distinct from UserEvent)."""
    from backend.app.services.lifestyle.a3_schedule_i8_projection import (
        build_lifestyle_i8_schedule_projection,
    )

    return APIResponse(
        ok=True, data=build_lifestyle_i8_schedule_projection(db, auth_user.id)
    )


@router.get("/weekly-plan", response_model=APIResponse)
def lifestyle_weekly_plan(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Read-only 7-day I8 nutrition/exercise projection. No generation side effects."""
    from backend.app.services.lifestyle.a3_weekly_plan_projection import (
        build_lifestyle_weekly_plan_projection,
    )

    return APIResponse(
        ok=True, data=build_lifestyle_weekly_plan_projection(db, auth_user.id)
    )


class ActionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str = Field(..., description="done | skipped")
    reason: Optional[str] = Field(None, description="no_time|too_hard|not_feeling_well|dont_like|forgot|other")


@router.post("/actions/{action_id}/review", response_model=APIResponse)
def lifestyle_action_review(
    action_id: int,
    payload: ActionReviewRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """End-of-day/week review of one I8 plan action (owner only): done or skipped (+ bounded reason)."""
    from backend.app.services.i8.action_review import ActionReviewError, record_review

    try:
        data = record_review(
            db, actor_user_id=auth_user.id, action_id=action_id, outcome=payload.outcome, reason=payload.reason
        )
    except ActionReviewError as exc:
        status = 404 if exc.code == "ACTION_NOT_FOUND" else (403 if exc.code == "ACTION_OWNER_MISMATCH" else 422)
        raise HTTPException(status_code=status, detail=exc.code)
    return APIResponse(ok=True, data=data)


def _plan_domain(domain: str) -> str:
    if domain not in ("nutrition", "exercise"):
        raise HTTPException(status_code=422, detail="DOMAIN_INVALID")
    return domain


class PlanSettingsRequest(BaseModel):
    """Any subset of the reminder / weekly-review settings of one plan (ISO weekdays 1=Mon..7=Sun; lead = minutes before)."""

    model_config = ConfigDict(extra="forbid")
    days: Optional[List[int]] = None
    lead: Optional[int] = Field(None, description="null = reminders off; 0 | 15 | 30")
    review_weekday: Optional[int] = None
    review_time: Optional[str] = Field(None, min_length=5, max_length=5, description="HH:MM")


@router.get("/plan-settings", response_model=APIResponse)
def lifestyle_plan_settings(
    domain: str = Query("nutrition", description="nutrition|exercise"),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from backend.app.services.i8.plan_settings import get_plan_settings

    return APIResponse(ok=True, data={"domain": _plan_domain(domain), "settings": get_plan_settings(db, auth_user.id, domain)})


@router.put("/plan-settings", response_model=APIResponse)
def lifestyle_plan_settings_save(
    payload: PlanSettingsRequest,
    domain: str = Query("nutrition", description="nutrition|exercise"),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reminder days / lead and the weekly-review day of one plan (stored in I6, applied to the plan's items)."""
    from backend.app.services.i8.plan_settings import PlanSettingsError, save_plan_settings

    _plan_domain(domain)
    patch = payload.model_dump(exclude_unset=True)
    try:
        settings = save_plan_settings(db, auth_user.id, domain, patch)
    except PlanSettingsError as exc:
        raise HTTPException(status_code=422, detail=exc.code)
    except ConsentDenied:
        return APIResponse(ok=False, error=ErrorInfo(code="CONSENT_DENIED", message="Memory consent required."))
    except MemoryWriteError as exc:
        return APIResponse(ok=False, error=ErrorInfo(code="MEMORY_WRITE_ERROR", message=str(exc)))
    return APIResponse(ok=True, data={"domain": domain, "settings": settings})


class PlanBuildRequest(BaseModel):
    """The setup sheet: the same fields Sedi asks in chat. Everything is optional; the allergy answer is required for meals."""

    model_config = ConfigDict(extra="forbid")
    domain: str = "nutrition"
    goal: Optional[str] = Field(None, max_length=120)
    avoid: Optional[str] = Field(None, max_length=240, description="foods to avoid (free text)")
    allergies: Optional[str] = Field(None, max_length=240)
    no_allergies: Optional[bool] = None
    meal_times: Optional[Dict[str, str]] = Field(None, description="breakfast|lunch|dinner|snack -> HH:MM")
    exercise_time: Optional[str] = Field(None, min_length=5, max_length=5)
    settings: Optional[PlanSettingsRequest] = None
    mode: str = Field("simple", description="simple (one plan) | pro (nutrition + exercise from one set of answers)")
    exercise_days: Optional[List[int]] = Field(None, description="pro mode: the workout weekdays (ISO 1..7)")


@router.post("/plan/build", response_model=APIResponse)
def lifestyle_plan_build(
    payload: PlanBuildRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build (or adjust) this week's plan right from the setup sheet, with the same composer chat uses."""
    from backend.app.services.i8.plan_builder import PlanBuildError, build_plan, build_pro
    from backend.app.services.i8.plan_settings import PlanSettingsError

    _plan_domain(payload.domain)
    if payload.mode not in ("simple", "pro"):
        raise HTTPException(status_code=422, detail="MODE_INVALID")
    setup = payload.model_dump(exclude_unset=True, exclude={"domain", "settings", "mode"})
    setup["settings"] = payload.settings.model_dump(exclude_unset=True) if payload.settings else {}
    try:
        data = build_pro(db, auth_user.id, setup) if payload.mode == "pro" else build_plan(db, auth_user.id, payload.domain, setup)
    except (PlanBuildError, PlanSettingsError) as exc:
        raise HTTPException(status_code=422, detail=exc.code)
    except ConsentDenied:
        return APIResponse(ok=False, error=ErrorInfo(code="CONSENT_DENIED", message="Memory consent required."))
    except MemoryWriteError as exc:
        return APIResponse(ok=False, error=ErrorInfo(code="MEMORY_WRITE_ERROR", message=str(exc)))
    return APIResponse(ok=True, data=data)


@router.get("/weekly-review", response_model=APIResponse)
def lifestyle_weekly_review(
    domain: str = Query("nutrition", description="nutrition|exercise"),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """How the current week went, from what the user marked (read-only)."""
    from backend.app.services.i8.weekly_review import build_weekly_review

    lang = (getattr(auth_user, "preferred_language", None) or "fa")
    return APIResponse(ok=True, data=build_weekly_review(db, auth_user.id, _plan_domain(domain), language=lang))


@router.get("/plan-progress", response_model=APIResponse)
def lifestyle_plan_progress(
    domain: str = Query("exercise", description="nutrition|exercise"),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The motivation panel: this week's sessions, the week strip, streak weeks, total and best, and Sedi's line (read-only)."""
    from backend.app.services.i8.plan_stats import build_progress

    lang = (getattr(auth_user, "preferred_language", None) or "fa")
    return APIResponse(ok=True, data=build_progress(db, auth_user.id, _plan_domain(domain), language=lang))


class ActionEditRequest(BaseModel):
    """The user's own correction of one plan item: any subset of time, title, note, duration (exercise)."""

    model_config = ConfigDict(extra="forbid")
    local_time: Optional[str] = Field(None, min_length=5, max_length=5, description="HH:MM, the user's local time")
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    note: Optional[str] = Field(None, max_length=240)
    duration_minutes: Optional[int] = Field(None, ge=5, le=180)


class ActionReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(..., min_length=1, max_length=64, description="An item_id offered by /alternatives")


def _action_edit_http_error(exc) -> HTTPException:
    status = 404 if exc.code == "ACTION_NOT_FOUND" else (403 if exc.code == "ACTION_OWNER_MISMATCH" else 422)
    return HTTPException(status_code=status, detail=exc.code)


@router.patch("/actions/{action_id}", response_model=APIResponse)
def lifestyle_action_edit(
    action_id: int,
    payload: ActionEditRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The user corrects one plan item: time, title, note or duration (owner only, ACTIVE items only)."""
    from backend.app.services.i8.action_edit import ActionEditError, edit_action

    try:
        data = edit_action(
            db,
            actor_user_id=auth_user.id,
            action_id=action_id,
            local_time=payload.local_time,
            title=payload.title,
            note=payload.note,
            duration_minutes=payload.duration_minutes,
        )
    except ActionEditError as exc:
        raise _action_edit_http_error(exc)
    return APIResponse(ok=True, data=data)


@router.get("/actions/{action_id}/alternatives", response_model=APIResponse)
def lifestyle_action_alternatives(
    action_id: int,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Up to 3 other catalogue items that fit this item's slot and the user's allergies / dislikes / limits."""
    from backend.app.services.i8.action_edit import ActionEditError, list_alternatives

    try:
        items = list_alternatives(db, actor_user_id=auth_user.id, action_id=action_id)
    except ActionEditError as exc:
        raise _action_edit_http_error(exc)
    return APIResponse(ok=True, data={"alternatives": items})


@router.post("/actions/{action_id}/replace", response_model=APIResponse)
def lifestyle_action_replace(
    action_id: int,
    payload: ActionReplaceRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The user swaps this item for one of its alternatives (an item the rules would not have refused)."""
    from backend.app.services.i8.action_edit import ActionEditError, replace_action_item

    try:
        data = replace_action_item(db, actor_user_id=auth_user.id, action_id=action_id, item_id=payload.item_id)
    except ActionEditError as exc:
        raise _action_edit_http_error(exc)
    return APIResponse(ok=True, data=data)


@router.delete("/actions/{action_id}", response_model=APIResponse)
def lifestyle_action_remove(
    action_id: int,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The user takes one plan item out of this week (owner only, ACTIVE items only)."""
    from backend.app.services.i8.action_edit import ActionEditError, remove_action

    try:
        data = remove_action(db, actor_user_id=auth_user.id, action_id=action_id)
    except ActionEditError as exc:
        raise _action_edit_http_error(exc)
    return APIResponse(ok=True, data=data)


def _require_admin(request: Request) -> None:
    """Fail-closed admin guard: ADMIN_TOKEN must be set; X-Admin-Token must match."""
    expected = os.environ.get("ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="admin_disabled")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != expected:
        raise HTTPException(status_code=403, detail="forbidden")


# -------------------- Request/Response Models --------------------

class LifestyleEntry(BaseModel):
    """Single lifestyle fact entry"""
    domain: str = Field(..., description="Memory domain (e.g., 'lifestyle')")
    key: str = Field(..., description="Fact key (e.g., 'sleep_duration_hours')")
    value: Any = Field(..., description="Fact value (will be stored as JSON)")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence score")
    source: str = Field(default="manual", description="Source: 'chat' | 'device' | 'manual'")


class LifestyleUpdateRequest(BaseModel):
    """Request model for lifestyle update (authenticated user only; no user_id)."""

    model_config = ConfigDict(extra="forbid")

    entries: List[LifestyleEntry] = Field(..., description="List of lifestyle facts to update")
    health_subject_id: Optional[int] = Field(
        None,
        description="If set and not SELF, rejected — Lifestyle OTHER not supported without schema",
    )


def _reject_other_lifestyle_subject(db: Session, account_user_id: int, health_subject_id: Optional[int]) -> None:
    """SELF-only lifestyle: OTHER health_subject_id fail-closed (no SELF data under OTHER)."""
    if health_subject_id is None:
        return
    from backend.app.services.i9.health_subject_service import (
        HealthSubjectAccessDenied,
        require_account_subject_access,
        resolve_canonical_active_self_subject,
    )

    try:
        subject = require_account_subject_access(db, account_user_id, int(health_subject_id))
    except HealthSubjectAccessDenied as exc:
        raise HTTPException(status_code=403, detail="health_subject_id not authorized") from exc
    self_subject = resolve_canonical_active_self_subject(db, account_user_id)
    is_self = self_subject is not None and int(self_subject.id) == int(subject.id)
    if not is_self:
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "error": {
                    "code": "LIFESTYLE_OTHER_UNSUPPORTED",
                    "message": "Lifestyle is available for SELF HealthSubject only",
                },
            },
        )


# -------------------- Endpoints --------------------

@router.post("/update", response_model=APIResponse)
def update_lifestyle(
    request: LifestyleUpdateRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update lifestyle facts for the authenticated user.

    Upserts facts into UserMemoryFact (domain+key unique per user).
    Requires Bearer JWT. user_id is derived from the token only.
    """
    _reject_other_lifestyle_subject(db, auth_user.id, request.health_subject_id)
    user_id = auth_user.id
    updated_facts = []
    errors = []

    for entry in request.entries:
        try:
            fact = write_fact(
                db,
                user_id,
                entry.domain,
                entry.key,
                entry.value,
                source=entry.source,
                provenance_class="USER_STATED",
                commit=True,
            )
            updated_facts.append({
                "domain": fact.domain,
                "key": fact.key,
                "fact_id": fact.id,
            })
        except ConsentDenied:
            errors.append(f"Consent denied ({entry.domain}/{entry.key})")
        except MemoryWriteError as e:
            errors.append(f"Invalid entry ({entry.domain}/{entry.key}): {str(e)}")
        except Exception as e:
            errors.append(f"Error updating {entry.domain}/{entry.key}: {str(e)}")

    if errors:
        return APIResponse(
            ok=False,
            error=ErrorInfo(
                code="UPDATE_ERROR",
                message=f"Some entries failed: {', '.join(errors)}",
            ),
            data={"updated": updated_facts, "errors": errors},
        )

    return APIResponse(
        ok=True,
        data={
            "updated_count": len(updated_facts),
            "facts": updated_facts,
        },
    )


@router.get("/context", response_model=APIResponse)
def get_lifestyle_context(
    health_subject_id: Optional[int] = Query(default=None),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get compact memory context for the authenticated user (SELF only if subject set)."""
    _reject_other_lifestyle_subject(db, auth_user.id, health_subject_id)
    context = build_memory_context(db, auth_user.id)
    return APIResponse(ok=True, data=context.to_dict())


# -------------------- GET /lifestyle/summary (Stage 17.1) --------------------
@router.get("/summary", response_model=APIResponse)
def get_lifestyle_summary(
    auth_user: models.User = Depends(get_current_user),
    lang: str = Query("en", description="Response language: en, fa, ar"),
    health_subject_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Get lifestyle summary for frontend display.
    Composes: What I know, Recent patterns, Next suggested check-in.
    Requires Bearer JWT. OTHER subject fail-closed.
    """
    _reject_other_lifestyle_subject(db, auth_user.id, health_subject_id)
    data = generate_summary(db, auth_user.id, language=lang)
    return APIResponse(ok=True, data=data)


# -------------------- Admin: GET /lifestyle/admin/candidates --------------------
@router.get("/admin/candidates", response_model=APIResponse)
def admin_list_candidates(
    request: Request,
    user_id: int = Query(..., description="User ID"),
    status: str = Query("pending", description="Filter by status: pending, accepted, rejected"),
    db: Session = Depends(get_db),
):
    """Admin: List fact candidates for a user. Requires configured ADMIN_TOKEN and matching X-Admin-Token."""
    _require_admin(request)
    rows = (
        db.query(models.UserFactCandidate)
        .filter(
            models.UserFactCandidate.user_id == user_id,
            models.UserFactCandidate.status == status,
        )
        .order_by(models.UserFactCandidate.created_at.desc())
        .limit(100)
        .all()
    )
    items = [
        {
            "id": r.id,
            "domain": r.domain,
            "key": r.key,
            "value_json": r.value_json,
            "confidence": r.confidence,
            "is_explicit": r.is_explicit,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return APIResponse(ok=True, data={"candidates": items, "count": len(items)})


# -------------------- Admin: POST /lifestyle/admin/candidates/{id}/decision --------------------
class CandidateDecisionRequest(BaseModel):
    status: str = Field(..., description="accepted or rejected")


@router.post("/admin/candidates/{candidate_id}/decision", response_model=APIResponse)
def admin_candidate_decision(
    request: Request,
    candidate_id: int,
    body: CandidateDecisionRequest,
    db: Session = Depends(get_db),
):
    """Admin: Accept or reject a fact candidate. Requires configured ADMIN_TOKEN and matching X-Admin-Token."""
    _require_admin(request)
    if body.status not in ("accepted", "rejected"):
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_STATUS", message="status must be accepted or rejected"))
    cand = db.query(models.UserFactCandidate).filter(models.UserFactCandidate.id == candidate_id).first()
    if not cand:
        return APIResponse(ok=False, error=ErrorInfo(code="NOT_FOUND", message="Candidate not found."))
    if body.status == "accepted":
        from backend.app.services.memory.memory_contract import MemoryContract

        valid, err = MemoryContract.validate_fact(cand.domain, cand.key)
        if not valid:
            return APIResponse(
                ok=False,
                error=ErrorInfo(code="INVALID_FACT", message=err or "Invalid fact"),
            )
        try:
            import json

            val = json.loads(cand.value_json)
            write_fact(
                db,
                cand.user_id,
                cand.domain,
                cand.key,
                val,
                source="chat",
                provenance_class="USER_CONFIRMED",
                commit=False,
            )
        except ConsentDenied:
            return APIResponse(
                ok=False,
                error=ErrorInfo(code="CONSENT_DENIED", message="Memory consent required."),
            )
        except MemoryWriteError as e:
            return APIResponse(
                ok=False,
                error=ErrorInfo(code="MEMORY_WRITE_ERROR", message=str(e)),
            )
        except Exception as e:
            return APIResponse(
                ok=False,
                error=ErrorInfo(code="WRITE_ERROR", message=str(e)),
            )
    cand.status = body.status
    db.add(cand)
    db.commit()
    return APIResponse(ok=True, data={"id": candidate_id, "status": body.status})


# -------------------- Admin: GET /lifestyle/admin/source_preview --------------------
@router.get("/admin/source_preview", response_model=APIResponse)
def admin_source_preview(
    request: Request,
    type: str = Query(..., description="Source type: daily_summary, user_fact, user_memory_fact, user_profile_knowledge, memory_turn, candidate_fact"),
    id: int = Query(..., description="Source record ID"),
    db: Session = Depends(get_db),
):
    """Admin: Safe preview of a source for debugging and RAG validation. Requires configured ADMIN_TOKEN and matching X-Admin-Token."""
    _require_admin(request)
    preview: Optional[Dict[str, Any]] = None
    if type == "daily_summary":
        row = db.query(models.DailyMemorySummary).filter(models.DailyMemorySummary.id == id).first()
        if row:
            s = (row.summary or "")[:200]
            preview = {"date": row.created_at.isoformat() if row.created_at else None, "snippet": s}
    elif type == "user_fact":
        row = db.query(models.UserFact).filter(models.UserFact.id == id).first()
        if row:
            preview = {"key": row.key, "value_json": row.value_json}
    elif type == "user_memory_fact":
        row = db.query(models.UserMemoryFact).filter(models.UserMemoryFact.id == id).first()
        if row:
            preview = {"domain": row.domain, "key": row.key, "value_json": row.value_json}
    elif type == "user_profile_knowledge":
        row = db.query(models.UserProfileKnowledge).filter(models.UserProfileKnowledge.id == id).first()
        if row:
            s = (row.baseline_summary or "")[:200]
            preview = {"snippet": s, "updated_at": row.updated_at.isoformat() if row.updated_at else None}
    elif type == "memory_turn":
        row = db.query(models.Memory).filter(models.Memory.id == id).first()
        if row:
            preview = {"created_at": row.created_at.isoformat() if row.created_at else None}
    elif type == "candidate_fact":
        row = db.query(models.UserFactCandidate).filter(models.UserFactCandidate.id == id).first()
        if row:
            preview = {"domain": row.domain, "key": row.key, "value_json": row.value_json}
    else:
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_TYPE", message=f"Unknown type: {type}"))
    if not preview:
        return APIResponse(ok=False, error=ErrorInfo(code="NOT_FOUND", message=f"Source not found: type={type}, id={id}"))
    return APIResponse(ok=True, data={"type": type, "id": id, "preview": preview})
