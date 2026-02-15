# app/routers/knowledge_admin.py
"""Knowledge Capture V1 admin API. Protected with X-Admin-Token when ADMIN_TOKEN is set."""
import os
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.services.knowledge.service import (
    create_candidate,
    accept_candidate,
    reject_candidate,
    list_user_facts,
    apply_answer,
)
from backend.app.schemas.knowledge import KcCandidateCreate, KcCandidateRead, KcUserFactRead, ApplyAnswerRequest

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_admin(request: Request) -> None:
    """Require X-Admin-Token header when ADMIN_TOKEN env is set. 404 if no token; 401 if mismatch."""
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _ensure_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# -------------------- POST /knowledge/admin/candidates/create --------------------
@router.post("/candidates/create", response_model=KcCandidateRead)
def admin_create_candidate(
    request: Request,
    payload: KcCandidateCreate,
    db: Session = Depends(get_db),
):
    """Create a fact candidate (for testing). Requires X-Admin-Token when ADMIN_TOKEN set."""
    _require_admin(request)
    _ensure_user(db, payload.user_id)
    row = create_candidate(
        db=db,
        user_id=payload.user_id,
        source=payload.source,
        fact_type=payload.fact_type,
        value_json=payload.value_json,
        confidence=payload.confidence,
        evidence=payload.evidence,
    )
    return row


# -------------------- POST /knowledge/admin/candidates/{id}/accept --------------------
@router.post("/candidates/{candidate_id:int}/accept", response_model=KcUserFactRead)
def admin_accept_candidate(
    request: Request,
    candidate_id: int,
    verified_by: str = Query("system", description="user | system | clinician"),
    db: Session = Depends(get_db),
):
    """Accept a pending candidate: upsert into kc_user_facts, close previous valid_to."""
    _require_admin(request)
    fact = accept_candidate(db=db, candidate_id=candidate_id, verified_by=verified_by)
    if not fact:
        raise HTTPException(status_code=404, detail="Candidate not found or not pending")
    return fact


# -------------------- POST /knowledge/admin/candidates/{id}/reject --------------------
@router.post("/candidates/{candidate_id:int}/reject")
def admin_reject_candidate(
    request: Request,
    candidate_id: int,
    db: Session = Depends(get_db),
):
    """Reject a pending candidate."""
    _require_admin(request)
    ok = reject_candidate(db=db, candidate_id=candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found or not pending")
    return {"ok": True}


# -------------------- POST /knowledge/admin/answers/apply --------------------
@router.post("/answers/apply")
def admin_apply_answer(
    request: Request,
    payload: ApplyAnswerRequest,
    db: Session = Depends(get_db),
):
    """
    Apply an answer for testing. If field_key is profile_core column -> update user_profile_core.
    Else -> create candidate + accept into kc_user_facts with verified_by=user.
    """
    _require_admin(request)
    _ensure_user(db, payload.user_id)
    try:
        result = apply_answer(db=db, user_id=payload.user_id, field_key=payload.field_key, value=payload.value)
        return {"ok": True, **result}
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------- GET /knowledge/admin/users/{user_id}/facts --------------------
@router.get("/users/{user_id:int}/facts", response_model=List[KcUserFactRead])
def admin_get_user_facts(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    """List verified facts for a user."""
    _require_admin(request)
    _ensure_user(db, user_id)
    rows = list_user_facts(db=db, user_id=user_id)
    return rows
