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
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get compact memory context for the authenticated user.

    Returns a MemoryContext built from UserMemoryFact (sleep/hydration/activity/mood/preferences if available).
    Requires Bearer JWT.
    """
    context = build_memory_context(db, auth_user.id)
    return APIResponse(ok=True, data=context.to_dict())


# -------------------- GET /lifestyle/summary (Stage 17.1) --------------------
@router.get("/summary", response_model=APIResponse)
def get_lifestyle_summary(
    auth_user: models.User = Depends(get_current_user),
    lang: str = Query("en", description="Response language: en, fa, ar"),
    db: Session = Depends(get_db),
):
    """
    Get lifestyle summary for frontend display.
    Composes: What I know, Recent patterns, Next suggested check-in.
    Requires Bearer JWT.
    """
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
