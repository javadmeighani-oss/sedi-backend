# app/routers/memory.py
"""
Memory router: daily summary (save/latest) + chat history from Memory table.
GET /memory/history - grouped conversation history for UI (daily/weekly/monthly/yearly).
"""
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.memory import (
    HistoryResponse,
    HistoryGroupItem,
    HistoryTurnItem,
    MemorySaveRequest,
)
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()

# Max rows to fetch from DB for grouping (avoid loading unbounded history)
_HISTORY_FETCH_CAP = 1000

GroupKind = Literal["daily", "weekly", "monthly", "yearly"]


def _reject_legacy_user_id_query(request: Request) -> None:
    """Reject legacy user_id query param; identity comes from JWT only."""
    if request.query_params.get("user_id") is not None:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "extra_forbidden",
                    "loc": ["query", "user_id"],
                    "msg": "Extra inputs are not permitted",
                    "input": request.query_params.get("user_id"),
                }
            ],
        )


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
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    group: GroupKind = Query("daily", description="Group by: daily | weekly | monthly | yearly"),
    limit: int = Query(200, ge=1, le=500, description="Max number of groups to return"),
    offset: int = Query(0, ge=0, description="Skip this many groups (pagination)"),
    db: Session = Depends(get_db),
):
    """
    Fetch chat history from Memory table, grouped by day/week/month/year.
    Requires Bearer JWT; user identity is derived from the token only.
    """
    rows = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == auth_user.id)
        .order_by(models.Memory.created_at.desc())
        .limit(_HISTORY_FETCH_CAP)
        .all()
    )

    rows_asc = list(reversed(rows))
    buckets = defaultdict(list)
    for m in rows_asc:
        key = _group_key(m.created_at, group)
        buckets[key].append(m)

    sorted_keys = sorted(buckets.keys(), reverse=True)
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


@router.post("/save", response_model=APIResponse)
def save_memory(
    body: MemorySaveRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save daily memory summary for the authenticated user.
    Requires Bearer JWT. user_id is derived from the token only.
    """
    memory_summary = models.DailyMemorySummary(
        user_id=auth_user.id,
        summary=body.summary or "",
        mood=body.mood,
        context=body.context,
        last_interaction=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    db.add(memory_summary)
    db.commit()
    db.refresh(memory_summary)

    return APIResponse(ok=True, data={"memory_id": memory_summary.id})


@router.get("/latest", response_model=APIResponse)
def get_latest_memory(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """
    Return the latest daily memory summary for the authenticated user.
    Requires Bearer JWT. user_id is derived from the token only.
    """
    record = (
        db.query(models.DailyMemorySummary)
        .filter(models.DailyMemorySummary.user_id == auth_user.id)
        .order_by(models.DailyMemorySummary.created_at.desc())
        .first()
    )

    if not record:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_MEMORY", message="No memory record found."))

    data = {
        "summary": record.summary,
        "mood": record.mood,
        "context": record.context,
        "last_interaction": record.last_interaction.isoformat() if record.last_interaction else None,
    }

    return APIResponse(ok=True, data=data)
