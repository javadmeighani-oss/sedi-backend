# app/routers/knowledge.py
"""Knowledge Capture V1 public API. No admin token required."""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.knowledge import ExtractFromMessageRequest, ApplyAnswerRequest
from backend.app.services.knowledge.question_engine import get_next_question
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.app.services.knowledge.service import apply_answer
from backend.app.services.knowledge.kc_fatigue_policy import (
    check_can_ask,
    mark_asked,
    mark_answer,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _ensure_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/next_question", response_model=APIResponse)
def get_next_question_endpoint(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """
    Get the best next question to ask the user for proactive data collection.
    Returns data=null with ok=true when no question needed.
    When blocked by fatigue control: status=no_question, reason=fatigue_control, next_eligible_at, policy.
    """
    _ensure_user(db, user_id)
    now = datetime.utcnow()
    allowed, reason, next_eligible_at, policy_snapshot = check_can_ask(db, user_id, now)
    if not allowed:
        data = {
            "status": "no_question",
            "reason": reason,
            "next_eligible_at": next_eligible_at.isoformat() if next_eligible_at else None,
            "policy": policy_snapshot,
        }
        return APIResponse(ok=True, data=data, error=None)
    data = get_next_question(db=db, user_id=user_id)
    if data is not None:
        question_type = (data.get("question_type") or "").strip() or "profile_question"
        mark_asked(db, user_id, now, question_type)
        data["policy"] = check_can_ask(db, user_id, now)[3]
    return APIResponse(ok=True, data=data, error=None)


@router.post("/extract_from_message", response_model=APIResponse)
def extract_from_message(
    payload: ExtractFromMessageRequest,
    db: Session = Depends(get_db),
):
    """
    Extract facts from chat message and create/auto-accept candidates.
    Response: { ok, data: { extracted_count, created_candidates_count, auto_accepted_count, ignored_count }, error }
    """
    _ensure_user(db, payload.user_id)
    result = process_message(
        db=db,
        user_id=payload.user_id,
        text=payload.text,
        language=payload.language,
        source_message_id=payload.source_message_id,
    )
    return APIResponse(ok=True, data=result, error=None)


@router.post("/apply_answer", response_model=APIResponse)
def apply_answer_endpoint(
    payload: ApplyAnswerRequest,
    db: Session = Depends(get_db),
):
    """
    Apply user answer. For confirm_candidate: pass candidate_id, question_type="confirm_candidate", value=Yes/No.
    For profile/fact: pass field_key and value (admin apply has full support).
    """
    _ensure_user(db, payload.user_id)
    try:
        # For confirm_candidate: use answer if present, else value
        raw_value = payload.value
        if payload.candidate_id is not None and (payload.question_type or "").strip().lower() == "confirm_candidate":
            a = payload.answer if (payload.answer is not None and str(payload.answer).strip()) else payload.value
            raw_value = a
        result = apply_answer(
            db=db,
            user_id=payload.user_id,
            field_key=payload.field_key,
            value=raw_value,
            candidate_id=payload.candidate_id,
            question_type=payload.question_type,
        )
        outcome = result.get("outcome")
        if outcome is not None:
            now = datetime.utcnow()
            mark_answer(db, payload.user_id, now, outcome)
            _, _, _, policy_snapshot = check_can_ask(db, payload.user_id, now)
            result = {**result, "policy": policy_snapshot}
        return APIResponse(ok=True, data=result, error=None)
    except (ValueError, TypeError) as e:
        return APIResponse(ok=False, data=None, error=ErrorInfo(code="INVALID_INPUT", message=str(e)))
