# app/routers/memory.py
"""
Memory router: daily summary (save/latest) + chat history from Memory table.
GET /memory/history - grouped conversation history for UI (daily/weekly/monthly/yearly).
"""
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone

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
from backend.app.services.gate4.policy_prefs_bridge import (
    get_local_now,
    resolve_validated_user_timezone,
)

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


def _as_utc_aware(created_at: datetime | None) -> datetime:
    """Treat naive DB timestamps as UTC; return timezone-aware UTC."""
    if created_at is None:
        return datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def _group_key_local(local_dt: datetime, group: GroupKind) -> str:
    """Return grouping key for a user-local datetime."""
    if group == "daily":
        return local_dt.strftime("%Y-%m-%d")
    if group == "weekly":
        year, week, _ = local_dt.isocalendar()
        return f"{year}-W{week:02d}"
    if group == "monthly":
        return local_dt.strftime("%Y-%m")
    if group == "yearly":
        return local_dt.strftime("%Y")
    return local_dt.strftime("%Y-%m-%d")


def _group_key_from_utc(created_at: datetime, group: GroupKind, tz_name: str) -> str:
    """Group a UTC (or naive-as-UTC) timestamp in the user's resolved timezone."""
    utc_dt = _as_utc_aware(created_at)
    local_dt = get_local_now(utc_dt, tz_name)
    return _group_key_local(local_dt, group)


def _current_group_key(now_utc: datetime, group: GroupKind, tz_name: str) -> str:
    """Current grouping bucket key from UTC now converted to user timezone."""
    local_now = get_local_now(now_utc, tz_name)
    return _group_key_local(local_now, group)


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
    tz_name = resolve_validated_user_timezone(db, auth_user.id)
    now_utc = datetime.now(timezone.utc)

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
        key = _group_key_from_utc(m.created_at, group, tz_name)
        buckets[key].append(m)

    sorted_keys = sorted(buckets.keys(), reverse=True)
    paginated_keys = sorted_keys[offset : offset + limit]

    items = []
    for key in paginated_keys:
        turns = [
            HistoryTurnItem(
                id=m.id,
                created_at=_as_utc_aware(m.created_at),
                user_message=m.user_message or "",
                sedi_response=m.sedi_response,
                language=m.language or "en",
            )
            for m in buckets[key]
        ]
        items.append(HistoryGroupItem(key=key, turns=turns))

    return HistoryResponse(
        group=group,
        timezone=tz_name,
        current_group_key=_current_group_key(now_utc, group, tz_name),
        items=items,
    )


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
