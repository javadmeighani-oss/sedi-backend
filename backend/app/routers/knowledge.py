# app/routers/knowledge.py
"""Knowledge Capture V1 public API. No admin token required."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.services.knowledge.question_engine import get_next_question

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
