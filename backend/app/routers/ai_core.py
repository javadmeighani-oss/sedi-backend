# app/routers/ai_core.py
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.core.ai_text_engine import generate_notification_text, NOTIF_TYPE_HEALTH_CHECK
from backend.app.services.notification_engine import DecisionEngine
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()


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


def _require_admin_if_set(request: Request) -> None:
    admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not admin_token:
        raise HTTPException(status_code=403, detail="admin_disabled")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != admin_token:
        raise HTTPException(status_code=401, detail="Admin token required")


def _parse_vital(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_analysis_summary(avg_hr: float, avg_temp: float, avg_spo2: float) -> str:
    return (
        f"heart_rate={round(avg_hr, 1)}, "
        f"temperature={round(avg_temp, 1)}, "
        f"spo2={round(avg_spo2, 1)}"
    )


@router.post("/analyze", response_model=APIResponse)
def analyze_health_data(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """
    Analyze recent health data for the authenticated user and create a smart notification.

    Requires Bearer JWT; user identity is derived from the token only.
    """
    user = auth_user
    user_id = user.id

    health_data = (
        db.query(models.HealthData)
        .filter(models.HealthData.user_id == user_id)
        .order_by(models.HealthData.created_at.desc())
        .limit(5)
        .all()
    )

    if not health_data:
        return APIResponse(ok=False, error=ErrorInfo(code="NO_DATA", message="No health data found."))

    avg_hr = sum(_parse_vital(d.heart_rate) for d in health_data) / len(health_data)
    avg_temp = sum(_parse_vital(d.temperature) for d in health_data) / len(health_data)
    avg_spo2 = sum(_parse_vital(d.spo2) for d in health_data) / len(health_data)

    notif_message = generate_notification_text(
        language=user.preferred_language or "en",
        notification_type=NOTIF_TYPE_HEALTH_CHECK,
        user_name=user.name or "User",
        health_summary=_build_analysis_summary(avg_hr, avg_temp, avg_spo2),
    )

    decision_engine = DecisionEngine(db)
    notif = decision_engine.create_insight_notification(
        user_id=user.id,
        insight_text=notif_message,
        priority="normal",
    )

    memory = models.Memory(
        user_id=user.id,
        user_message=(
            f"Health analyzed: HR={round(avg_hr, 1)}, "
            f"Temp={round(avg_temp, 1)}, SpO2={round(avg_spo2, 1)}"
        ),
        sedi_response=notif_message,
        language=user.preferred_language or "en",
        created_at=datetime.utcnow(),
    )
    db.add(memory)
    db.commit()

    print(f"[AI CORE] Notification created for user_id={user.id}: {notif.body}")

    return APIResponse(
        ok=True,
        data={
            "user_id": user.id,
            "language": user.preferred_language,
            "notification": {
                "id": notif.id,
                "type": notif.type,
                "title": notif.title,
                "body": notif.body,
                "priority": notif.priority,
            },
        },
    )


# -------------------- Admin: GET /ai_core/admin/rag_breaker (Stage 17.9) --------------------
@router.get("/admin/rag_breaker", response_model=APIResponse)
def admin_rag_breaker(request: Request):
    """Admin: Circuit breaker state for vector RAG guardrails."""
    _require_admin_if_set(request)
    from backend.app.services.local_rag.circuit_breaker import get_state

    return APIResponse(ok=True, data=get_state())


# -------------------- Admin: GET /ai_core/admin/rag_metrics (Stage 17.7) --------------------
@router.get("/admin/rag_metrics", response_model=APIResponse)
def admin_rag_metrics(request: Request):
    """Admin: RAG retrieval metrics snapshot. Requires X-Admin-Token if ADMIN_TOKEN set."""
    _require_admin_if_set(request)
    from backend.app.services.local_rag.metrics import get_metrics

    data = get_metrics().snapshot()
    return APIResponse(ok=True, data=data)


# -------------------- Admin: POST /ai_core/admin/index_daily_summaries (Stage 17.8) --------------------
@router.post("/admin/index_daily_summaries", response_model=APIResponse)
def admin_index_daily_summaries(
    request: Request,
    user_id: int = Query(..., description="User ID to index"),
    days: int = Query(30, description="Days of summaries to index"),
    db: Session = Depends(get_db),
):
    """Admin: Index daily summaries for a user into rag_embeddings."""
    _require_admin_if_set(request)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))
    try:
        from backend.app.services.local_rag.indexing import index_daily_summaries_for_user

        result = index_daily_summaries_for_user(db, user_id, days=days)
        return APIResponse(ok=True, data={"user_id": user_id, "indexed": result["indexed"], "skipped": result["skipped"], "failed": result["failed"]})
    except Exception as e:
        return APIResponse(ok=False, error=ErrorInfo(code="INDEX_ERROR", message=str(e)))


# -------------------- Admin: POST /ai_core/admin/index_daily_summaries_all (Stage 17.8) --------------------
@router.post("/admin/index_daily_summaries_all", response_model=APIResponse)
def admin_index_daily_summaries_all(
    request: Request,
    days: int = Query(30, description="Days of summaries to index"),
    limit: int = Query(50, description="Max users per batch"),
    offset: int = Query(0, description="Offset for batch"),
    db: Session = Depends(get_db),
):
    """Admin: Index daily summaries for a batch of users (controlled rollout)."""
    _require_admin_if_set(request)
    try:
        from backend.app.services.local_rag.indexing import index_daily_summaries_all as index_all

        result = index_all(db, days=days, limit=limit, offset=offset)
        return APIResponse(ok=True, data=result)
    except Exception as e:
        return APIResponse(ok=False, error=ErrorInfo(code="INDEX_ERROR", message=str(e)))


# -------------------- Admin: POST /ai_core/admin/reindex_embeddings (Stage 17.6) --------------------
@router.post("/admin/reindex_embeddings", response_model=APIResponse)
def admin_reindex_embeddings(
    request: Request,
    user_id: int = Query(..., description="User ID to index"),
    db: Session = Depends(get_db),
):
    """Admin: Trigger embedding indexing for a user. Requires RAG_VECTOR_REBUILD=true. Best effort."""
    _require_admin_if_set(request)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))
    try:
        from backend.app.services.local_rag.indexing import index_embeddings_for_user

        result = index_embeddings_for_user(db, user_id)
        return APIResponse(ok=True, data={"user_id": user_id, "result": result})
    except Exception as e:
        return APIResponse(ok=False, error=ErrorInfo(code="INDEX_ERROR", message=str(e)))
