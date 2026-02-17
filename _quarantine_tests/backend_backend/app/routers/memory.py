# app/routers/memory.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo

router = APIRouter()


@router.post("/save", response_model=APIResponse)
def save_memory(payload: dict, db: Session = Depends(get_db)):
    """
    ذخیره حافظه روزانه کاربر
    {
        "user_id": 1,
        "summary": "User walked 5000 steps, slept 6 hours, HR avg 82 bpm.",
        "mood": "neutral",
        "context": "Slight fatigue reported"
    }
    """
    user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    memory = models.Memory(
        user_id=user.id,
        summary=payload.get("summary"),
        mood=payload.get("mood"),
        context=payload.get("context"),
        last_interaction=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)

    return APIResponse(ok=True, data={"memory_id": memory.id})


@router.get("/latest", response_model=APIResponse)
def get_latest_memory(user_id: int, db: Session = Depends(get_db)):
    """
    دریافت آخرین حافظه ثبت‌شده برای کاربر
    """
    record = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user_id)
        .order_by(models.Memory.created_at.desc())
        .first()
    )

    if not record:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_MEMORY", message="No memory record found."))

    data = {
        "summary": record.summary,
        "mood": record.mood,
        "context": record.context,
        "last_interaction": record.last_interaction.isoformat()
    }

    return APIResponse(ok=True, data=data)
