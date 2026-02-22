# app/routers/knowledge.py
"""Knowledge Capture V1 public API. No admin token required."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo, ApiResponseV1
from backend.app.schemas.knowledge import ExtractFromMessageRequest, ApplyAnswerRequest
from backend.app.services.knowledge.question_engine import get_next_question
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.app.services.knowledge.service import apply_answer
from backend.app.services.knowledge.kc_fatigue_policy import (
    check_can_ask,
    mark_asked,
    mark_answer,
)
from backend.app.knowledge.tone import apply_companion_tone

router = APIRouter()
logger = logging.getLogger(__name__)

# KC → Notification Bridge: best-effort idempotency window (no new migrations)
_KC_NOTIFY_DEDUPE_MINUTES = 10
_KC_NOTIFICATION_TYPE = "kc_confirm"
_KC_CHANNEL = "engagement"
_DEFAULT_KC_TITLE_FA = "یه سوال کوتاه"
_DEFAULT_KC_TITLE_EN = "Quick question"


_KC_DELIVER_PENDING_LIMIT = 1  # Minimize latency; do not deliver up to 10 in same request


def _maybe_send_kc_notification(
    db: Session,
    user_id: int,
    data: Dict[str, Any],
    lang: str,
    in_app: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    When data is confirm_candidate with display_* fields, create notification (and optionally deliver).
    Best-effort idempotency via dedupe_key; errors are non-fatal.
    in_app=True: create inbox record only, do not call deliver_pending (user active in app).
    Returns: { attempted: bool, ok: bool, reason?: str, notification_id?: int }.
    Reasons: dedupe_skip | in_app_skip_delivery | created_and_delivered | created_pending | error.
    """
    result: Dict[str, Any] = {"attempted": False, "ok": False}
    if (data.get("question_type") or "").strip().lower() != "confirm_candidate":
        return result
    body = (data.get("display_body") or "").strip()
    if not body:
        result["attempted"] = True
        result["reason"] = "missing_display_body"
        return result
    candidate_id = data.get("candidate_id")
    title = (data.get("display_title") or "").strip()
    if not title:
        title = _DEFAULT_KC_TITLE_EN if (lang or "").strip().lower() in ("en", "en-us", "en-gb") else _DEFAULT_KC_TITLE_FA

    dedupe_key = f"kc_confirm:{user_id}:confirm_candidate:{candidate_id}"

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=_KC_NOTIFY_DEDUPE_MINUTES)
        existing = (
            db.query(models.Notification)
            .filter(
                models.Notification.user_id == user_id,
                models.Notification.dedupe_key == dedupe_key,
                models.Notification.created_at >= cutoff,
            )
            .first()
        )
        if existing is not None:
            result["attempted"] = True
            result["ok"] = True
            result["reason"] = "dedupe_skip"
            result["notification_id"] = existing.id
            return result

        now = datetime.utcnow()
        notif = models.Notification(
            user_id=user_id,
            type=_KC_NOTIFICATION_TYPE,
            title=title,
            body=body,
            priority="normal",
            is_read=False,
            is_sent=False,
            scheduled_for=now,
            dedupe_key=dedupe_key,
            channel=_KC_CHANNEL,
            language=(lang or "fa")[:20],
            status="queued",
            actions_json='[{"id":"open_chat","type":"OPEN_CHAT"}]',
            provider=None,
        )
        if candidate_id is not None:
            notif.deeplink_url = f"sedi://chat?from=kc&candidate_id={candidate_id}"
        db.add(notif)
        db.commit()
        db.refresh(notif)
        if not notif.deeplink_url:
            notif.deeplink_url = f"sedi://chat?from=notif&id={notif.id}"
            db.add(notif)
            db.commit()

        result["attempted"] = True
        result["ok"] = True
        result["notification_id"] = notif.id

        if in_app:
            result["reason"] = "in_app_skip_delivery"
            return result

        from backend.app.services.notifications.delivery_service import DeliveryService
        delivery = DeliveryService(db=db)
        delivery.deliver_pending(limit=_KC_DELIVER_PENDING_LIMIT)
        result["reason"] = "created_and_delivered"
        return result
    except Exception as e:
        logger.warning("kc_notify_failed user_id=%s candidate_id=%s error=%s", user_id, candidate_id, str(e))
        result["attempted"] = True
        result["ok"] = False
        result["reason"] = (str(e) or "error")[:200]
        return result


def _ensure_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _resolve_lang(lang_query: Optional[str], user: models.User) -> str:
    """Language: query param > user.preferred_language > default 'fa'."""
    if lang_query is not None and (str(lang_query).strip().lower() in ("fa", "en", "en-us", "en-gb")):
        return str(lang_query).strip().lower()
    if user and getattr(user, "preferred_language", None):
        return (str(user.preferred_language).strip().lower() or "fa")[:5]
    return "fa"


@router.get("/next_question", response_model=ApiResponseV1)
def get_next_question_endpoint(
    user_id: int = Query(..., description="User ID"),
    lang: Optional[str] = Query(None, description="Display language: fa | en"),
    notify: bool = Query(False, description="If true and response is confirm_candidate, send a notification"),
    in_app: bool = Query(False, description="If true with notify=true: create inbox notification only, skip push delivery (user active in app)"),
    db: Session = Depends(get_db),
):
    """
    Get the best next question to ask the user for proactive data collection.
    Never returns data=null: when no question is available, returns status=no_question, reason=no_available_question with policy.
    When blocked by fatigue control: status=no_question, reason=fatigue_control, next_eligible_at, policy.
    Optional display fields (display_title, display_body, display_choices, tone_version) when confirm_candidate.
    When notify=true and response is confirm_candidate, enqueues/sends a notification (optional data.notification).
    When in_app=true with notify=true, notification is created but deliver_pending is not called.
    Example: GET /knowledge/next_question?user_id=1&lang=fa&notify=true
    """
    user = _ensure_user(db, user_id)
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
    if data is None:
        _, _, next_eligible_at, policy_snapshot = check_can_ask(db, user_id, now)
        return APIResponse(
            ok=True,
            data={
                "status": "no_question",
                "reason": "no_available_question",
                "next_eligible_at": next_eligible_at.isoformat() if next_eligible_at else None,
                "policy": policy_snapshot,
            },
            error=None,
        )
    question_type = (data.get("question_type") or "").strip() or "profile_question"
    mark_asked(db, user_id, now, question_type)
    data["policy"] = check_can_ask(db, user_id, now)[3]
    resolved_lang = _resolve_lang(lang, user)
    if question_type == "confirm_candidate":
        data = apply_companion_tone(data, lang=resolved_lang)
    try:
        from backend.app.behavior import apply_behavior_to_question
        data = apply_behavior_to_question(db, user_id, data, resolved_lang)
    except Exception:
        pass
    if notify and question_type == "confirm_candidate":
        try:
            data["notification"] = _maybe_send_kc_notification(db, user_id, data, resolved_lang, in_app)
        except Exception as e:
            logger.warning("kc_notify_bridge_error user_id=%s error=%s", user_id, str(e))
            data["notification"] = {"attempted": True, "ok": False, "reason": (str(e) or "error")[:200]}
    return APIResponse(ok=True, data=data, error=None)


@router.post("/extract_from_message", response_model=ApiResponseV1)
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


@router.post("/apply_answer", response_model=ApiResponseV1)
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
        # Prefer payload.value, but fall back to payload.answer (for profile/fact and confirm_candidate)
        raw_value = payload.value
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            if payload.answer is not None and str(payload.answer).strip():
                raw_value = payload.answer

        # For confirm_candidate: explicitly prefer answer when present
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
