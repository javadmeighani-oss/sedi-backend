# app/routers/notifications.py
"""
Notification Router - Backend API for Notification System

Supports:
- Medication reminders
- Condition-based (disease-aware) care notifications
- Future scheduler integration (scheduled_for field is queryable)
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Literal
from datetime import datetime, timedelta
import hashlib
import json as _json
import logging
import os

from backend.app.database import get_db
from backend.app.models import Notification, User, PushDevice, NotificationFeedback
from backend.app.schemas import APIResponse, ErrorInfo, NotificationResponse
from backend.app.schemas.notification import (
    NotificationCreate,
    NotificationFeedbackRequest,
    PushRegisterRequest,
    PushFeedbackActionRequest,
    TestPushRequest,
)

router = APIRouter()
_log = logging.getLogger(__name__)

DEFAULT_ACTIONS_JSON = '[{"id":"like","type":"LIKE"},{"id":"dislike","type":"DISLIKE"},{"id":"open_chat","type":"OPEN_CHAT"}]'


def _is_placeholder_or_invalid_fcm_token(token: str) -> bool:
    """Reject placeholder or invalid FCM tokens (Stage 19 token hygiene)."""
    if not token:
        return True
    t = token.strip()
    if not t:
        return True
    upper = t.upper()
    if "PASTE_" in upper or "PASTE" in upper or "TOKEN" in upper:
        return True
    if any(ch.isspace() for ch in t):
        return True
    if len(t) < 80:
        return True
    return False


def _token_hash(token: str) -> str:
    """Short hash for logging only; never log raw token (Stage 19)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _require_admin_if_set(request: Request) -> None:
    """If ADMIN_TOKEN env is set, require X-Admin-Token header. Same pattern as deliver_pending."""
    admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
    if admin_token:
        header_token = (request.headers.get("X-Admin-Token") or "").strip()
        if header_token != admin_token:
            raise HTTPException(status_code=401, detail="Admin token required")


# ------------------ GET /notifications/admin/push_devices (Stage 16.6.1) ------------------
@router.get("/admin/push_devices", response_model=APIResponse)
def admin_list_push_devices(
    request: Request,
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """
    Admin-only: List push devices for a user. Returns masked tokens (first 6 + last 4).
    """
    _require_admin_if_set(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    devices = (
        db.query(PushDevice)
        .filter(PushDevice.user_id == user_id, PushDevice.is_active == True)  # noqa: E712
        .all()
    )
    items = []
    for d in devices:
        tok = d.fcm_token or ""
        masked = f"{tok[:6]}...{tok[-4:]}" if len(tok) >= 11 else "***"
        items.append({
            "id": d.id,
            "platform": d.platform,
            "token_masked": masked,
            "device_id": d.device_id,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        })
    _log.info("[E2E] admin push_devices user_id=%s count=%s", user_id, len(items))
    return APIResponse(ok=True, data={"devices": items, "count": len(items)})


# ------------------ POST /notifications/admin/test_push (Stage 16.6.1) ------------------
@router.post("/admin/test_push", response_model=APIResponse)
def admin_test_push(
    request: Request,
    body: TestPushRequest,
    deliver: bool = Query(False, description="If true, run deliver_pending after enqueue"),
    db: Session = Depends(get_db),
):
    """
    Admin-only: Enqueue a test push for a user. Uses unique dedupe_key so it always sends.
    Optionally run delivery when deliver=true.
    """
    _require_admin_if_set(request)
    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    import uuid
    now = datetime.utcnow()
    lang = user.preferred_language or "en"
    title = body.title or f"Test {body.channel}"
    body_text = body.body or f"E2E test notification ({body.channel})"
    dedupe_key = f"admin_test:{body.user_id}:{uuid.uuid4().hex}"
    deeplink_url = None  # Will be set after persist

    notif = Notification(
        user_id=body.user_id,
        type=body.channel,
        title=title,
        body=body_text,
        priority=body.priority,
        is_read=False,
        is_sent=False,
        scheduled_for=now,
        dedupe_key=dedupe_key,
        channel=body.channel,
        language=lang,
        actions_json=DEFAULT_ACTIONS_JSON,
        provider=None,
        status="queued",
        ttl_seconds=body.ttl_seconds,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    notif.deeplink_url = f"sedi://chat?from=notif&id={notif.id}"
    db.add(notif)
    db.commit()

    sent_count = 0
    if deliver:
        from backend.app.services.notifications.delivery_service import DeliveryService
        service = DeliveryService(db=db)
        sent_count = service.deliver_pending(limit=10)

    _log.info(
        "[E2E] admin test_push user_id=%s channel=%s notification_id=%s deliver=%s sent=%s",
        body.user_id, body.channel, notif.id, deliver, sent_count,
    )
    return APIResponse(
        ok=True,
        data={
            "notification_id": notif.id,
            "channel": body.channel,
            "delivered": deliver,
            "sent_count": sent_count,
        }
    )


# ------------------ POST /notifications/admin/notif/send_now (Stage 18) ------------------
SEND_NOW_CHANNELS = Literal["morning", "engagement", "health_alert"]


def _mask_token(t: str) -> str:
    """Mask FCM token for logs: first 6 + last 4. Do not log full tokens."""
    if not t or len(t) < 11:
        return "***"
    return f"{t[:6]}...{t[-4:]}"


def _get_user_tz_for_log(db: Session, user_id: int) -> str:
    """Resolve user timezone string for structured logs."""
    from backend.app.services.memory import MemoryRepository
    repo = MemoryRepository(db)
    tz_fact = repo.get_fact(user_id=user_id, domain="preferences", key="timezone")
    if not tz_fact or not tz_fact.value_json:
        return "Asia/Tehran"
    try:
        tz_data = _json.loads(tz_fact.value_json)
        return tz_data.get("tz", "Asia/Tehran") if isinstance(tz_data, dict) else "Asia/Tehran"
    except (_json.JSONDecodeError, TypeError):
        return "Asia/Tehran"


@router.post("/admin/notif/send_now", response_model=APIResponse)
def admin_notif_send_now(
    request: Request,
    user_id: int = Query(..., description="User ID"),
    channel: SEND_NOW_CHANNELS = Query(..., description="Channel: morning | engagement | health_alert"),
    force: bool = Query(False, description="If true, bypass quiet hours and anti-spam"),
    template_key: Optional[str] = Query(None, description="If set, use V1 template for title/body instead of ad-hoc"),
    db: Session = Depends(get_db),
):
    """
    Admin-only: Deterministic push debug path. Send one push to user's tokens for the given channel.
    If template_key is provided, title/body are rendered from that V1 template (language from user).
    Returns attempted_tokens, sent_success, sent_fail, reasons, fcm_errors. On NO_TOKENS or policy
    skip returns 200 with reason; does not create a notification row.
    """
    _require_admin_if_set(request)
    _log.info("event=send_now channel=%s user_id=%s template_key=%s", channel, user_id, template_key)
    from backend.app.services.notifications.delivery_service import _get_fcm_tokens_for_user
    from backend.app.services.notifications.fcm_client import (
        send_push_to_tokens,
        parse_fcm_error,
        FCM_DEACTIVATE_ERROR_CODES,
    )
    from backend.app.services.notification_runtime.quiet_hours import is_within_quiet_hours

    # Validate user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )

    tokens = _get_fcm_tokens_for_user(db, user_id, limit=20)
    tz_str = _get_user_tz_for_log(db, user_id)
    priority = "high" if channel == "health_alert" else "normal"
    in_quiet = is_within_quiet_hours(db, user_id, channel, priority)
    tokens_masked = [_mask_token(t) for t in tokens]

    _log.info(
        "[NOTIF][SEND] user_id=%s channel=%s force=%s tokens=%s tz=%s quiet_hours=%s",
        user_id, channel, force, tokens_masked, tz_str, in_quiet,
    )

    if not tokens:
        _log.info("[NOTIF][SKIP] user_id=%s channel=%s reason=NO_TOKENS", user_id, channel)
        return APIResponse(
            ok=True,
            data={
                "user_id": user_id,
                "channel": channel,
                "force": force,
                "attempted_tokens": 0,
                "sent_success": 0,
                "sent_fail": 0,
                "reasons": ["NO_TOKENS"],
                "fcm_errors": [],
            },
        )

    if not force:
        if in_quiet:
            _log.info("[NOTIF][SKIP] user_id=%s channel=%s reason=QUIET_HOURS", user_id, channel)
            return APIResponse(
                ok=True,
                data={
                    "user_id": user_id,
                    "channel": channel,
                    "force": force,
                    "attempted_tokens": len(tokens),
                    "sent_success": 0,
                    "sent_fail": 0,
                    "reasons": ["QUIET_HOURS"],
                    "fcm_errors": [],
                },
            )
        # Anti-spam: engagement channel — min hours since last engagement
        if channel == "engagement":
            engagement_min_h = int(os.getenv("ENGAGEMENT_MIN_HOURS", "3"))
            min_ago = datetime.utcnow() - timedelta(hours=engagement_min_h)
            last_engagement = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.channel == "engagement",
                    Notification.created_at >= min_ago,
                )
                .order_by(Notification.created_at.desc())
                .first()
            )
            if last_engagement:
                _log.info("[NOTIF][SKIP] user_id=%s channel=%s reason=ANTI_SPAM", user_id, channel)
                return APIResponse(
                    ok=True,
                    data={
                        "user_id": user_id,
                        "channel": channel,
                        "force": force,
                        "attempted_tokens": len(tokens),
                        "sent_success": 0,
                        "sent_fail": 0,
                        "reasons": ["ANTI_SPAM"],
                        "fcm_errors": [],
                    },
                )

    # Send Guard V1: when template_key present, run full guard (pause, quiet_hours, dedup, cap)
    if template_key:
        from backend.app.services.notification_runtime.templates_v1 import get_template_v1
        from backend.app.services.notification_runtime.language_resolver import resolve_effective_language
        from backend.app.services.notifications.send_guard_v1 import can_send_v1
        tpl = get_template_v1(template_key)
        channel_for_guard = tpl.get("channel", channel) if tpl else channel
        priority_guard = "high" if channel_for_guard == "health_alert" else "normal"
        effective_lang = resolve_effective_language(db, user_id) if tpl else None
        guard = can_send_v1(
            db, user_id, channel_for_guard, template_key, priority_guard,
            datetime.utcnow(), language=effective_lang, force=force,
        )
        if not guard["allowed"]:
            _log.info("[NOTIF][SEND] user_id=%s template_key=%s blocked reasons=%s", user_id, template_key, guard["reasons"])
            data_blocked = {
                "user_id": user_id,
                "channel": channel,
                "force": force,
                "attempted_tokens": len(tokens),
                "sent_success": 0,
                "sent_fail": 0,
                "blocked": True,
                "reasons": guard["reasons"],
                "fcm_errors": [],
            }
            if guard.get("paused_until") is not None:
                data_blocked["paused_until"] = guard["paused_until"]
            if guard.get("dedupe_key") is not None:
                data_blocked["dedupe_key"] = guard["dedupe_key"]
            return APIResponse(ok=True, data=data_blocked)
    # Build title/body: from V1 template if template_key provided, else ad-hoc
    title = "Sedi"
    body = f"Debug send_now ({channel})"
    if template_key:
        from backend.app.services.notification_runtime.templates_v1 import get_template_v1
        from backend.app.services.notification_runtime.renderer import render
        from backend.app.services.notification_runtime.language_resolver import resolve_effective_language
        tpl = get_template_v1(template_key)
        if tpl:
            from backend.app.services.notification_runtime.user_context_adapter import build_notification_context
            user_ctx = build_notification_context(db, user_id)
            effective_lang = (user_ctx.get("language") or resolve_effective_language(db, user_id))
            if effective_lang not in ("en", "fa", "ar"):
                effective_lang = "en"
            rendered = render(
                channel=tpl.get("channel", "engagement"),
                language=effective_lang,
                inputs={"user_display_name": user_ctx.get("preferred_name") or getattr(user, "name", None)},
                priority="high" if channel == "health_alert" else "normal",
                template=tpl,
                user_ctx=user_ctx,
            )
            title = (rendered.get("title") or "").strip() or title
            body = (rendered.get("body") or "").strip() or body
    data = {"channel": channel, "type": channel, "notification_id": ""}
    project_id = os.getenv("FCM_PROJECT_ID", "").strip()

    success_count, results = send_push_to_tokens(
        tokens=tokens,
        title=title,
        body=body,
        data=data,
        android_priority=priority,
        ttl_seconds=3600,
        project_id=project_id or None,
        timeout_sec=None,
    )

    reasons: List[str] = []
    fcm_errors: List[dict] = []
    sent_fail = 0

    for fcm_token, msg_id, err in results:
        err_parsed = parse_fcm_error(err) if err else None
        err_code = (err_parsed or {}).get("code", "OK" if not err else "UNKNOWN")
        err_message = (err_parsed or {}).get("message", err or "")
        status = "ok" if not err else "error"
        _log.info(
            "[NOTIF][FCM] user_id=%s channel=%s project_id=%s status=%s err_code=%s request_id=%s",
            user_id, channel, project_id or "", status, err_code, msg_id or "",
        )
        if err:
            sent_fail += 1
            fcm_errors.append({"code": err_code, "message": err_message})
            if err_parsed and err_parsed.get("code") in FCM_DEACTIVATE_ERROR_CODES:
                dev = db.query(PushDevice).filter(
                    PushDevice.fcm_token == fcm_token,
                    PushDevice.user_id == user_id,
                ).first()
                if dev:
                    dev.is_active = False
                    dev.updated_at = datetime.utcnow()
                    db.add(dev)
                    reasons.append(f"token_deactivated:{err_code}")

    db.commit()

    sent_success = success_count
    return APIResponse(
        ok=True,
        data={
            "user_id": user_id,
            "channel": channel,
            "force": force,
            "attempted_tokens": len(tokens),
            "sent_success": sent_success,
            "sent_fail": sent_fail,
            "reasons": reasons if reasons else [],
            "fcm_errors": fcm_errors,
        },
    )


# ------------------ POST /notifications/admin/companion_ping/send_now (Behavior V1) ------------------
@router.post("/admin/companion_ping/send_now", response_model=APIResponse)
def admin_companion_ping_send_now(
    request: Request,
    user_id: int = Query(..., description="User ID"),
    language: Optional[str] = Query(None, description="Language (fa, en, ar); optional"),
    db: Session = Depends(get_db),
):
    """
    Admin-only: Trigger Behavior V1 companion_ping for server tests.
    Uses DecisionEngine.create_companion_ping; respects quiet hours and daily budget.
    Returns ok=true, created (bool), notification_id (nullable), deeplink (nullable).
    """
    _require_admin_if_set(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."),
        )
    from backend.app.services.notification_engine import DecisionEngine
    engine = DecisionEngine(db)
    notif = engine.create_companion_ping(user_id, language=language)
    if notif is None:
        return APIResponse(
            ok=True,
            data={"created": False, "notification_id": None, "deeplink": None},
        )
    return APIResponse(
        ok=True,
        data={
            "created": True,
            "notification_id": notif.id,
            "deeplink": notif.deeplink_url,
            "type": "companion_ping",
        },
    )


# ------------------ GET /notifications/admin/templates/list ------------------
@router.get("/admin/templates/list", response_model=APIResponse)
def admin_templates_list(request: Request):
    """Admin-only: List V1 template keys and basic fields."""
    _require_admin_if_set(request)
    from backend.app.services.notification_runtime.templates_v1 import list_templates_v1
    items = list_templates_v1()
    return APIResponse(ok=True, data={"templates": items, "count": len(items)})


# ------------------ GET /notifications/admin/templates/preview ------------------
@router.get("/admin/templates/preview", response_model=APIResponse)
def admin_templates_preview(
    request: Request,
    template_key: str = Query(..., description="Template key"),
    user_id: Optional[int] = Query(None, description="User ID (for language resolution; optional)"),
    lang: str = Query("fa", description="Language code (fa, en, ar)"),
    db: Session = Depends(get_db),
):
    """Admin-only: Preview template render without sending."""
    _require_admin_if_set(request)
    from backend.app.services.notification_runtime.templates_v1 import get_template_v1
    from backend.app.services.notification_runtime.renderer import render
    template = get_template_v1(template_key)
    if not template:
        return APIResponse(ok=False, error=ErrorInfo(code="TEMPLATE_NOT_FOUND", message=f"Template not found: {template_key}"))
    language = lang.strip().lower() if lang else "fa"
    user_ctx = {}
    if user_id:
        from backend.app.services.notification_runtime.language_resolver import resolve_effective_language
        from backend.app.services.notification_runtime.user_context_adapter import build_notification_context
        try:
            user_ctx = build_notification_context(db, user_id)
            language = (user_ctx.get("language") or resolve_effective_language(db=db, user_id=user_id) or language)
        except Exception:
            pass
    if language not in ("en", "fa", "ar"):
        language = "en"
    rendered = render(
        channel=template.get("channel", "engagement"),
        language=language,
        inputs={},
        priority=template.get("priority", "normal"),
        template=template,
        user_ctx=user_ctx,
    )
    return APIResponse(
        ok=True,
        data={
            "template": {
                "key": template.get("key"),
                "version": template.get("version"),
                "channel": template.get("channel"),
                "type": template.get("type"),
                "priority": template.get("priority"),
            },
            "rendered": {
                "title": rendered.get("title", ""),
                "body": rendered.get("body", ""),
                "actions_json": rendered.get("actions_json", ""),
            },
        },
    )


# ------------------ GET /notifications/admin/feedback_stats ------------------
@router.get("/admin/feedback_stats", response_model=APIResponse)
def admin_feedback_stats(
    request: Request,
    user_id: Optional[int] = Query(None, description="Filter by user ID (optional)"),
    days: int = Query(7, ge=1, le=90, description="Last N days"),
    db: Session = Depends(get_db),
):
    """
    Admin-only: Feedback stats for debugging and adaptive policy.
    Returns counts_by_event_type, counts_by_reason, last_events (max 20).
    """
    _require_admin_if_set(request)
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(NotificationFeedback).filter(NotificationFeedback.created_at >= since)
    if user_id is not None:
        q = q.filter(NotificationFeedback.user_id == user_id)
    rows = q.order_by(NotificationFeedback.created_at.desc()).limit(500).all()
    counts_by_event_type = {}
    counts_by_reason = {}
    for r in rows:
        counts_by_event_type[r.action] = counts_by_event_type.get(r.action, 0) + 1
        if r.meta_json:
            try:
                meta = _json.loads(r.meta_json)
                reason = meta.get("reason")
                if reason:
                    counts_by_reason[reason] = counts_by_reason.get(reason, 0) + 1
            except (_json.JSONDecodeError, TypeError):
                pass
    last_events = []
    for r in rows[:20]:
        meta = {}
        if r.meta_json:
            try:
                meta = _json.loads(r.meta_json)
            except (_json.JSONDecodeError, TypeError):
                pass
        last_events.append({
            "timestamp": r.created_at.isoformat() if r.created_at else None,
            "event_type": r.action,
            "reason": meta.get("reason"),
            "notification_id": r.notification_id,
        })
    return APIResponse(
        ok=True,
        data={
            "counts_by_event_type": counts_by_event_type,
            "counts_by_reason": counts_by_reason,
            "last_events": last_events,
            "days": days,
            "user_id": user_id,
        },
    )


# ------------------ GET /notifications/admin/adaptive_state ------------------
@router.get("/admin/adaptive_state", response_model=APIResponse)
def admin_adaptive_state(
    request: Request,
    user_id: int = Query(..., description="User ID"),
    days: int = Query(7, ge=1, le=90, description="Feedback window in days"),
    db: Session = Depends(get_db),
):
    """
    Admin-only: Adaptive policy state for companion channel (debug).
    Returns paused_until, companion_cap_override, counts, reasons_count, computed_at.
    """
    _require_admin_if_set(request)
    from backend.app.services.notifications.adaptive_policy_v1 import compute_adaptive_state
    now = datetime.utcnow()
    state = compute_adaptive_state(db, user_id, now, days)
    return APIResponse(ok=True, data=state)


# ------------------ GET /notifications/admin/health (Stage 16.6.2) ------------------
@router.get("/admin/health", response_model=APIResponse)
def admin_notification_health(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Admin-only: Lightweight notification subsystem health.
    Returns pending_count, failed_last_1h, last_deliver_pending_run_at.
    """
    _require_admin_if_set(request)
    from backend.app.services.notifications.delivery_service import (
        last_deliver_pending_run_at,
    )

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)

    pending_count = (
        db.query(Notification)
        .filter(Notification.is_sent == False)  # noqa: E712
        .filter(
            or_(Notification.scheduled_for.is_(None), Notification.scheduled_for <= now)
        )
        .count()
    )
    failed_last_1h = (
        db.query(Notification)
        .filter(Notification.status == "failed", Notification.created_at >= one_hour_ago)
        .count()
    )

    return APIResponse(
        ok=True,
        data={
            "notifications_pending_count": pending_count,
            "notifications_failed_last_1h": failed_last_1h,
            "last_deliver_pending_run_at": (
                last_deliver_pending_run_at.isoformat()
                if last_deliver_pending_run_at else None
            ),
        },
    )


# ------------------ GET /notifications?user_id={id} ------------------
@router.get("", response_model=APIResponse)
@router.get("/", response_model=APIResponse)
def get_notifications(
    user_id: int = Query(..., description="User ID to fetch notifications for"),
    db: Session = Depends(get_db)
):
    """
    Get all notifications for a user, ordered by created_at descending.
    
    Returns a list of notifications for the specified user_id.
    """
    # Validate user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    # Base query (no order/limit) for full counts
    base_query = db.query(Notification).filter(Notification.user_id == user_id)
    total = base_query.count()
    unread_count = base_query.filter(Notification.is_read == False).count()
    
    # Fetch list with ordering (no limit for this endpoint; pagination can be added later)
    notifications = (
        base_query
        .order_by(Notification.created_at.desc())
        .all()
    )
    
    # Convert to response format
    notification_list = [
        NotificationResponse(
            id=notif.id,
            user_id=notif.user_id,
            type=notif.type,
            title=notif.title,
            body=notif.body,
            priority=notif.priority,
            is_read=notif.is_read,
            is_sent=notif.is_sent,
            scheduled_for=notif.scheduled_for,
            created_at=notif.created_at
        )
        for notif in notifications
    ]

    return APIResponse(
        ok=True,
        data={
            "notifications": [n.dict() for n in notification_list],
            "total": total,
            "unread_count": unread_count,
        }
    )


# ------------------ GET /notifications/unread (Release B2) ------------------
@router.get("/unread", response_model=APIResponse)
def get_unread_notifications(
    user_id: int = Query(..., description="User ID to fetch unread notifications for"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of notifications to return"),
    type: Optional[str] = Query(None, description="Optional filter by notification type"),
    db: Session = Depends(get_db)
):
    """
    Get unread notifications for a user (Release B2).
    
    Returns list of notifications where is_read=false, ordered by created_at descending.
    Supports optional filtering by type and limit.
    """
    # Validate user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    # Build query for unread notifications
    query = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .filter(Notification.is_read == False)
    )
    
    # Apply type filter if provided
    if type:
        query = query.filter(Notification.type == type)
    
    # Total unread count (before limit) for contract total/unread_count
    unread_total = query.count()

    # Order by created_at desc and apply limit
    notifications = (
        query
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    
    # Convert to response format
    notification_list = [
        NotificationResponse(
            id=notif.id,
            user_id=notif.user_id,
            type=notif.type,
            title=notif.title,
            body=notif.body,
            priority=notif.priority,
            is_read=notif.is_read,
            is_sent=notif.is_sent,
            scheduled_for=notif.scheduled_for,
            created_at=notif.created_at
        )
        for notif in notifications
    ]
    
    return APIResponse(
        ok=True,
        data={
            "notifications": [n.dict() for n in notification_list],
            "count": len(notification_list),
            "total": unread_total,
            "unread_count": unread_total,
        }
    )


# ------------------ POST /notifications/{notification_id}/mark-read (Release B2) ------------------
@router.post("/{notification_id}/mark-read", response_model=APIResponse)
@router.post("/{notification_id}/read", response_model=APIResponse)  # Backward compatibility alias
def mark_notification_read(
    notification_id: int,
    user_id: int = Query(..., description="User ID (must own the notification)"),
    db: Session = Depends(get_db)
):
    """
    Mark a notification as read (Release B2).
    
    Updates the is_read field to True for the specified notification.
    Validates ownership: notification.user_id must match provided user_id.
    Idempotent: can be called multiple times safely.
    
    Endpoints:
    - POST /notifications/{id}/mark-read (new)
    - POST /notifications/{id}/read (backward compatible)
    """
    # Find notification
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="NOTIFICATION_NOT_FOUND", message="Notification not found.")
        )
    
    # Validate ownership
    if notification.user_id != user_id:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="FORBIDDEN", message="You do not have permission to modify this notification.")
        )
    
    # Mark as read (idempotent - safe to call multiple times)
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    
    # Return success response
    return APIResponse(
        ok=True,
        data={"ok": True, "notification_id": notification_id, "is_read": True}
    )


# ------------------ POST /notifications/push/register (Stage 16.6) ------------------
@router.post("/push/register", response_model=APIResponse)
def push_register(
    body: PushRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register or update FCM token for push notifications (Stage 16.6).
    Upsert by fcm_token; set user_id, is_active=True, last_seen_at=now.
    Fail-open for tests: accept any non-empty token (do not hard-validate format).
    """
    token = (body.fcm_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=400,
            detail="fcm_token required",
        )
    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    now = datetime.utcnow()
    existing = db.query(PushDevice).filter(PushDevice.fcm_token == token).first()
    if existing:
        existing.user_id = body.user_id
        existing.platform = body.platform
        existing.device_id = body.device_id or existing.device_id
        existing.is_active = True
        existing.last_seen_at = now
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        return APIResponse(
            ok=True,
            data={"ok": True, "device_id": existing.id, "updated": True}
        )
    device = PushDevice(
        user_id=body.user_id,
        platform=body.platform,
        fcm_token=token,
        device_id=body.device_id,
        is_active=True,
        last_seen_at=now,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return APIResponse(
        ok=True,
        data={"ok": True, "device_id": device.id}
    )


# ------------------ POST /notifications/push/unregister (Stage 16.6) ------------------
@router.post("/push/unregister", response_model=APIResponse)
def push_unregister(
    fcm_token: str = Query(..., description="FCM token to deactivate"),
    user_id: int = Query(..., description="User ID (must own the token)"),
    db: Session = Depends(get_db),
):
    """Deactivate a push device by FCM token (Stage 16.6)."""
    device = db.query(PushDevice).filter(
        PushDevice.fcm_token == fcm_token,
        PushDevice.user_id == user_id,
    ).first()
    if not device:
        return APIResponse(
            ok=True,
            data={"ok": True, "message": "Token not found or already inactive"}
        )
    device.is_active = False
    device.updated_at = datetime.utcnow()
    db.commit()
    return APIResponse(
        ok=True,
        data={"ok": True, "device_id": device.id, "message": "Token deactivated"}
    )


# ------------------ V1: Normalize reaction/action/feedback to event_type ------------------
def _normalize_feedback_payload(payload: dict) -> tuple:
    """
    Resolve reaction and event_type from contract + legacy payload.
    Returns (event_type: str, reaction_for_b2: str|None, reason: str|None, feedback_text, timestamp, action_id).
    event_type is one of: like, dislike, open, dismiss.
    """
    reaction = payload.get("reaction")
    action_legacy = payload.get("action")
    feedback_legacy = payload.get("feedback")
    # Resolve effective reaction (contract or legacy)
    if reaction in ("seen", "interact", "dismiss", "like", "dislike"):
        eff_reaction = reaction
    elif action_legacy in ("like", "dislike", "open_chat", "dismissed"):
        eff_reaction = {"like": "like", "dislike": "dislike", "open_chat": "open", "dismissed": "dismiss"}[action_legacy]
    elif feedback_legacy == "positive":
        eff_reaction = "like"
    elif feedback_legacy == "negative":
        eff_reaction = "dislike"
    elif feedback_legacy == "neutral":
        eff_reaction = "open"
    else:
        eff_reaction = "open"
    # Normalize to event_type (V1: like, dislike, open, dismiss)
    if eff_reaction in ("like", "dislike", "dismiss"):
        event_type = eff_reaction
    elif eff_reaction in ("seen", "interact"):
        event_type = "open"
    else:
        event_type = "open"
    reason = payload.get("reason")
    if reason and reason not in ("too_frequent", "irrelevant", "unclear"):
        reason = reason  # keep as string for meta
    feedback_text = payload.get("feedback_text")
    timestamp = payload.get("timestamp") or payload.get("client_ts")
    action_id = payload.get("action_id")
    return event_type, eff_reaction, reason, feedback_text, timestamp, action_id


# ------------------ POST /notifications/{notification_id}/feedback (Release B2 + Stage 16.6 + V1) ------------------
@router.post("/{notification_id}/feedback", response_model=APIResponse)
def submit_notification_feedback(
    notification_id: int,
    payload: dict,
    user_id: Optional[int] = Query(None, description="User ID (optional, validated from notification if not provided)"),
    db: Session = Depends(get_db)
):
    """
    Submit feedback for a notification. V1: normalized event_type (like/dislike/open/dismiss).
    Contract: reaction (required), timestamp (required), action_id (required when reaction==interact), feedback_text?, reason?.
    Legacy: feedback/action/client_ts/meta accepted and mapped. reason enum: too_frequent | irrelevant | unclear.
    """
    # Find notification
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="NOTIFICATION_NOT_FOUND", message="Notification not found.")
        )
    if user_id is None:
        user_id = notification.user_id
    elif user_id != notification.user_id:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="FORBIDDEN", message="You do not have permission to provide feedback for this notification.")
        )
    # V1: If reaction is interact, action_id is required (422)
    reaction_raw = payload.get("reaction")
    if reaction_raw == "interact" and not payload.get("action_id"):
        raise HTTPException(
            status_code=422,
            detail="action_id is required when reaction is 'interact'"
        )
    event_type, eff_reaction, reason, feedback_text, timestamp, action_id = _normalize_feedback_payload(payload)
    meta = {}
    if reason:
        meta["reason"] = reason
    if feedback_text is not None:
        meta["feedback_text"] = feedback_text
    if timestamp:
        meta["client_timestamp"] = timestamp
    if action_id:
        meta["action_id"] = action_id
    if payload.get("meta"):
        meta["legacy_meta"] = payload.get("meta")
    meta_json = _json.dumps(meta) if meta else None
    feedback_row = NotificationFeedback(
        notification_id=notification_id,
        user_id=user_id,
        action=event_type,
        meta_json=meta_json,
    )
    db.add(feedback_row)
    db.commit()
    # B2 morning_brief path: need feedback_request (positive/negative/neutral)
    feedback_type = "positive" if eff_reaction == "like" else ("negative" if eff_reaction == "dislike" else "neutral")
    feedback_request = type("FB", (), {"feedback": feedback_type, "reason": reason, "action": payload.get("action")})()
    # Check if this is a morning_brief notification
    is_morning_brief = (
        notification.type == "morning_brief" or
        "morning" in notification.body.lower() or 
        (notification.title and "morning" in notification.title.lower())
    )
    
    if is_morning_brief:
        # Handle morning_summary feedback
        from backend.app.services.memory import MemoryRepository
        import json
        
        memory_repo = MemoryRepository(db)
        
        # Get existing feedback fact
        feedback_fact = memory_repo.get_fact(
            user_id=notification.user_id,
            domain="preferences",
            key="morning_notification_feedback"
        )
        
        # Initialize or update feedback counters
        if feedback_fact:
            try:
                feedback_data = _json.loads(feedback_fact.value_json)
                positives = feedback_data.get("positives", feedback_data.get("likes", 0))  # Support old format
                negatives = feedback_data.get("negatives", feedback_data.get("dislikes", 0))  # Support old format
            except (_json.JSONDecodeError, KeyError, TypeError):
                positives = 0
                negatives = 0
        else:
            positives = 0
            negatives = 0
        
        # Update counters based on new standardized feedback
        if feedback_request.feedback == "positive":
            positives += 1
        elif feedback_request.feedback == "negative":
            negatives += 1
        # "neutral" doesn't affect counters
        
        # Store feedback
        feedback_data = {
            "positives": positives,
            "negatives": negatives,
            "last_feedback_at": datetime.utcnow().isoformat()
        }
        
        try:
            memory_repo.upsert_fact(
                user_id=user_id,
                domain="preferences",
                key="morning_notification_feedback",
                value=feedback_data,
                confidence=0.8,
                source="manual"
            )
        except Exception as e:
            print(f"[Feedback] Error storing feedback fact: {e}")
        
        # Adjust morning time if many negatives (safe, with logging)
        if negatives >= 3 and negatives > positives:
            # Get current morning time
            morning_time_fact = memory_repo.get_fact(
                user_id=notification.user_id,
                domain="preferences",
                key="morning_notification_time"
            )
            
            current_hour = 9  # Default
            current_minute = 0
            
            if morning_time_fact:
                try:
                    time_data = _json.loads(morning_time_fact.value_json)
                    current_hour = time_data.get("hour", 9)
                    current_minute = time_data.get("minute", 0)
                except (_json.JSONDecodeError, KeyError, TypeError):
                    pass
            
            # Shift +1 hour (cap between 6 and 11)
            new_hour = min(current_hour + 1, 11)
            if new_hour < 6:
                new_hour = 6
            
            if new_hour != current_hour:
                try:
                    memory_repo.upsert_fact(
                        user_id=user_id,
                        domain="preferences",
                        key="morning_notification_time",
                        value={"hour": new_hour, "minute": current_minute},
                        confidence=0.7,
                        source="manual"
                    )
                    print(f"[Feedback] Adjusted morning time for user {user_id} from {current_hour}:{current_minute:02d} to {new_hour}:{current_minute:02d} (reason: {negatives} negative feedbacks)")
                except Exception as e:
                    print(f"[Feedback] Error adjusting morning time for user {user_id}: {e}")
    
    return APIResponse(
        ok=True,
        data={
            "feedback_received": True,
            "message": "Feedback recorded",
            "notification_id": notification_id,
            "feedback": feedback_request.feedback,
            "message": "Feedback recorded successfully"
        }
    )


# ------------------ POST /notifications/deliver_pending (admin/dev) ------------------
@router.post("/deliver_pending", response_model=APIResponse)
def deliver_pending_notifications(
    request: Request,
    limit: int = Query(100, ge=1, le=500, description="Max number of unsent notifications to process"),
    db: Session = Depends(get_db),
):
    """
    Run the notification delivery pipeline: query unsent (is_sent=false),
    send via configured adapter, mark is_sent=true. Safe to call repeatedly.
    If ADMIN_TOKEN env is set, requires X-Admin-Token header (admin/dev pattern).
    """
    import os
    admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
    if admin_token:
        header_token = (request.headers.get("X-Admin-Token") or "").strip()
        if header_token != admin_token:
            return APIResponse(
                ok=False,
                error=ErrorInfo(code="UNAUTHORIZED", message="Admin token required.")
            )
    from backend.app.services.notifications.delivery_service import DeliveryService
    service = DeliveryService(db=db)
    sent_count = service.deliver_pending(limit=limit)
    return APIResponse(
        ok=True,
        data={"sent_count": sent_count, "message": f"Marked {sent_count} notification(s) as sent"}
    )


# ==================== SCHEDULER INTEGRATION READINESS ====================
# TODO: Future scheduler integration will query notifications with:
#   - scheduled_for <= current_time
#   - is_sent = False
#   - Then mark is_sent = True after sending
#
# Example query for scheduler:
#   scheduled_notifications = db.query(Notification).filter(
#       Notification.scheduled_for <= datetime.utcnow(),
#       Notification.is_sent == False
#   ).all()
#
# This allows the scheduler to:
#   - Find notifications ready to be sent
#   - Send them (via push notification, SMS, etc.)
#   - Mark them as sent to prevent duplicate sends
# =========================================================================
