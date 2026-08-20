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
from backend.app.services.i6.consent_service import (
    get_memory_consent_status,
    grant_memory_consent,
    revoke_memory_consent,
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


@router.get("/consent", response_model=APIResponse)
def get_memory_consent(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current memory-consent status for the authenticated user (JWT only)."""
    return APIResponse(ok=True, data=get_memory_consent_status(db, auth_user.id))


@router.post("/consent/grant", response_model=APIResponse)
def grant_memory_consent_endpoint(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Grant memory consent for the authenticated user (JWT only)."""
    grant_memory_consent(db, auth_user.id, commit=True)
    return APIResponse(ok=True, data=get_memory_consent_status(db, auth_user.id))


@router.post("/consent/revoke", response_model=APIResponse)
def revoke_memory_consent_endpoint(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke memory consent for the authenticated user (JWT only)."""
    revoked = revoke_memory_consent(db, auth_user.id, commit=True)
    status = get_memory_consent_status(db, auth_user.id)
    return APIResponse(ok=True, data={"revoked": revoked, **status})


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

    from backend.app.services.i7.retention import query_eligible_raw

    rows = query_eligible_raw(db, auth_user.id, now=now_utc, limit=_HISTORY_FETCH_CAP)

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
    Retire new product writes to legacy DailyMemorySummary.
    Canonical daily owner is UserPeriodSummary DAILY (I7-DEC-06).
    """
    from backend.app.services.i7.hierarchy import build_daily_from_raw

    try:
        row = build_daily_from_raw(db, auth_user.id, finalize=False, commit=True)
    except Exception as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # Optional narrative overlay when client still posts a summary string
    if body.summary:
        row.narrative_summary = body.summary
        db.commit()
        db.refresh(row)
    return APIResponse(
        ok=True,
        data={
            "memory_id": row.id,
            "canonical_owner": "UserPeriodSummary.DAILY",
            "legacy_dms_write": False,
        },
    )


@router.get("/latest", response_model=APIResponse)
def get_latest_memory(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Return the latest canonical UPS DAILY summary for the authenticated user."""
    from backend.app.services.i7.hierarchy import get_canonical_daily

    record = get_canonical_daily(db, auth_user.id)
    if not record:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_MEMORY", message="No memory record found."))

    data = {
        "summary": record.narrative_summary,
        "mood": None,
        "context": record.structured_summary_json,
        "last_interaction": record.generated_at.isoformat() if record.generated_at else None,
        "canonical_owner": "UserPeriodSummary.DAILY",
        "period_start": record.period_start.isoformat() if record.period_start else None,
        "finalized_at": record.finalized_at.isoformat() if record.finalized_at else None,
    }
    return APIResponse(ok=True, data=data)


@router.get("/period-summary", response_model=APIResponse)
def get_period_summary(
    auth_user: models.User = Depends(get_current_user),
    summary_type: str = Query("DAILY"),
    db: Session = Depends(get_db),
):
    """JWT-scoped historical period summary recall (summary != transcript)."""
    st = (summary_type or "DAILY").upper()
    if st not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        raise HTTPException(status_code=422, detail="Invalid summary_type")
    row = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == auth_user.id,
            models.UserPeriodSummary.summary_type == st,
            models.UserPeriodSummary.status == "active",
        )
        .order_by(models.UserPeriodSummary.period_start.desc())
        .first()
    )
    if row is None:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_SUMMARY", message="No period summary found."))
    return APIResponse(
        ok=True,
        data={
            "id": row.id,
            "summary_type": row.summary_type,
            "narrative_summary": row.narrative_summary,
            "structured_summary_json": row.structured_summary_json,
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "period_end": row.period_end.isoformat() if row.period_end else None,
            "period_timezone": row.period_timezone,
            "period_week_start": row.period_week_start,
            "finalized_at": row.finalized_at.isoformat() if row.finalized_at else None,
            "not_transcript": True,
        },
    )


@router.get("/lifelong", response_model=APIResponse)
def get_lifelong_recall(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.UserLifelongProfile)
        .filter(
            models.UserLifelongProfile.user_id == auth_user.id,
            models.UserLifelongProfile.status == "active",
        )
        .order_by(models.UserLifelongProfile.version.desc())
        .first()
    )
    if row is None:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_LIFELONG", message="No lifelong profile found."))
    return APIResponse(
        ok=True,
        data={
            "id": row.id,
            "version": row.version,
            "narrative_compact": row.narrative_compact,
            "structured_profile_json": row.structured_profile_json,
            "not_transcript": True,
        },
    )


@router.post("/export", response_model=APIResponse)
def create_memory_export(
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from backend.app.services.i7.export_jobs import create_export_job

    job = create_export_job(db, auth_user.id, actor_user_id=auth_user.id, commit=True)
    return APIResponse(ok=True, data={"job_id": job.id, "status": job.status})


@router.post("/forget", response_model=APIResponse)
def forget_memory_turn(
    memory_id: int = Query(...),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ownership-scoped delete/forget; purge when eligible, else explicit user forget."""
    import json
    from datetime import datetime, timezone

    from backend.app.services.i6.consent_service import PERM_FORGET, require_permission
    from backend.app.services.i7.purge import purge_expired_raw_turn

    require_permission(db, auth_user.id, PERM_FORGET)
    owned = (
        db.query(models.Memory)
        .filter(models.Memory.id == memory_id, models.Memory.user_id == auth_user.id)
        .first()
    )
    result = purge_expired_raw_turn(db, user_id=auth_user.id, memory_id=memory_id, commit=True)
    if result.purged:
        return APIResponse(ok=True, data={"forgotten": True, "reason": result.reason})
    if owned is None:
        raise HTTPException(status_code=404, detail="Memory not found for user")
    if result.reason in (
        "NOT_EXPIRED",
        "DAILY_NOT_FINALIZED",
        "PROVENANCE_MISSING",
        "NOT_DURABLE_GOVERNED",
    ):
        key = f"purge:user:{auth_user.id}:memory:{memory_id}"
        existing = (
            db.query(models.UserMemoryPurgeReceipt)
            .filter(models.UserMemoryPurgeReceipt.purge_key == key)
            .first()
        )
        if existing is None:
            receipt = models.UserMemoryPurgeReceipt(
                user_id=auth_user.id,
                memory_id=memory_id,
                local_period_date=owned.local_period_date,
                purge_key=key,
                purged_at=datetime.now(timezone.utc),
                reason="USER_FORGET",
                integrity_sha256=None,
                provenance_json=owned.provenance_json or json.dumps({"reason": "USER_FORGET"}),
            )
            db.delete(owned)
            db.add(receipt)
            db.commit()
        return APIResponse(ok=True, data={"forgotten": True, "reason": "USER_FORGET"})
    raise HTTPException(status_code=409, detail=result.reason)
