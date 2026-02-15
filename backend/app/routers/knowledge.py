# app/routers/knowledge.py
"""Knowledge Capture V1 public API. No admin token required."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.knowledge import ExtractFromMessageRequest, ApplyAnswerRequest
from backend.app.services.knowledge.question_engine import get_next_question
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.app.services.knowledge.service import apply_answer

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
    """
    _ensure_user(db, user_id)
    data = get_next_question(db=db, user_id=user_id)
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
        result = apply_answer(
            db=db,
            user_id=payload.user_id,
            field_key=payload.field_key,
            value=payload.value,
            candidate_id=payload.candidate_id,
            question_type=payload.question_type,
        )
        return APIResponse(ok=True, data=result, error=None)
    except (ValueError, TypeError) as e:
        return APIResponse(ok=False, data=None, error=ErrorInfo(code="INVALID_INPUT", message=str(e)))
