# app/routers/memory.py
"""
Memory router: daily summary (save/latest) + chat history from Memory table.
GET /memory/history - grouped conversation history for UI (daily/weekly/monthly/yearly).
"""
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.memory import (
    HistoryResponse,
    HistoryGroupItem,
    HistoryTurnItem,
)
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()

# Max rows to fetch from DB for grouping (avoid loading unbounded history)
_HISTORY_FETCH_CAP = 1000

GroupKind = Literal["daily", "weekly", "monthly", "yearly"]


def _group_key(created_at: datetime, group: GroupKind) -> str:
    """Return grouping key for a memory row."""
    if group == "daily":
        return created_at.strftime("%Y-%m-%d")
    if group == "weekly":
        year, week, _ = created_at.isocalendar()
        return f"{year}-W{week:02d}"
    if group == "monthly":
        return created_at.strftime("%Y-%m")
    if group == "yearly":
        return created_at.strftime("%Y")
    return created_at.strftime("%Y-%m-%d")


@router.get("/history", response_model=HistoryResponse)
def get_chat_history(
    user: models.User = Depends(get_current_user),
    user_id: int = Query(..., description="User ID (required)"),
    group: GroupKind = Query("daily", description="Group by: daily | weekly | monthly | yearly"),
    limit: int = Query(200, ge=1, le=500, description="Max number of groups to return"),
    offset: int = Query(0, ge=0, description="Skip this many groups (pagination)"),
    db: Session = Depends(get_db),
):
    """
    Fetch chat history from Memory table, grouped by day/week/month/year.
    Requires Bearer JWT; user_id query must match authenticated user.
    """
    if user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="user_id does not match authenticated user",
        )

    # Fetch memory rows for authenticated user only (strict filter)
    rows = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user.id)
        .order_by(models.Memory.created_at.desc())
        .limit(_HISTORY_FETCH_CAP)
        .all()
    )

    # Group by key (oldest-first within group: reverse then group)
    rows_asc = list(reversed(rows))
    buckets = defaultdict(list)
    for m in rows_asc:
        key = _group_key(m.created_at, group)
        buckets[key].append(m)

    # Sort groups by key descending (newest first)
    sorted_keys = sorted(buckets.keys(), reverse=True)
    # Paginate groups
    paginated_keys = sorted_keys[offset : offset + limit]

    items = []
    for key in paginated_keys:
        turns = [
            HistoryTurnItem(
                id=m.id,
                created_at=m.created_at or datetime.utcnow(),
                user_message=m.user_message or "",
                sedi_response=m.sedi_response,
                language=m.language or "en",
            )
            for m in buckets[key]
        ]
        items.append(HistoryGroupItem(key=key, turns=turns))

    return HistoryResponse(group=group, items=items)


# --- DailyMemorySummary endpoints (existing) ---


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

    # Use DailyMemorySummary instead of Memory
    memory_summary = models.DailyMemorySummary(
        user_id=user.id,
        summary=payload.get("summary", ""),
        mood=payload.get("mood"),
        context=payload.get("context"),
        last_interaction=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(memory_summary)
    db.commit()
    db.refresh(memory_summary)

    return APIResponse(ok=True, data={"memory_id": memory_summary.id})


@router.get("/latest", response_model=APIResponse)
def get_latest_memory(user_id: int, db: Session = Depends(get_db)):
    """
    دریافت آخرین حافظه ثبت‌شده برای کاربر
    """
    # Use DailyMemorySummary instead of Memory
    record = (
        db.query(models.DailyMemorySummary)
        .filter(models.DailyMemorySummary.user_id == user_id)
        .order_by(models.DailyMemorySummary.created_at.desc())
        .first()
    )

    if not record:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_MEMORY", message="No memory record found."))

    data = {
        "summary": record.summary,
        "mood": record.mood,
        "context": record.context,
        "last_interaction": record.last_interaction.isoformat() if record.last_interaction else None
    }

    return APIResponse(ok=True, data=data)


# ---------------------------------------------------------------------------
# curl examples for GET /memory/history (run with backend on http://localhost:8000)
# ---------------------------------------------------------------------------
#
# Daily grouping (default), user_id=1:
#   curl -s "http://localhost:8000/memory/history?user_id=1&group=daily&limit=20&offset=0"
#
# Weekly grouping:
#   curl -s "http://localhost:8000/memory/history?user_id=1&group=weekly&limit=50"
#
# Monthly grouping:
#   curl -s "http://localhost:8000/memory/history?user_id=1&group=monthly"
#
# Yearly grouping:
#   curl -s "http://localhost:8000/memory/history?user_id=1&group=yearly"
#
# Pagination (second page of 10 groups):
#   curl -s "http://localhost:8000/memory/history?user_id=1&group=daily&limit=10&offset=10"
#
# 404 when user does not exist:
#   curl -s "http://localhost:8000/memory/history?user_id=99999"
