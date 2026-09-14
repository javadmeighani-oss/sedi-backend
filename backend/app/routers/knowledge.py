# app/routers/knowledge.py
"""Knowledge Capture V1 user-facing API (JWT required)."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo, ApiResponseV1
from backend.app.schemas.knowledge import ExtractFromMessageUserRequest, ApplyAnswerUserRequest
from backend.app.services.knowledge.question_engine import get_next_question
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.app.services.knowledge.service import apply_answer
from backend.app.services.knowledge.kc_fatigue_policy import (
    check_can_ask,
    mark_asked,
    mark_answer,
)
from backend.app.knowledge.tone import apply_companion_tone
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

_KC_NOTIFY_DEDUPE_MINUTES = 10
_KC_NOTIFICATION_TYPE = "kc_confirm"
_KC_CHANNEL = "engagement"
_DEFAULT_KC_TITLE_FA = "یه سوال کوتاه"
_DEFAULT_KC_TITLE_EN = "Quick question"
_KC_DELIVER_PENDING_LIMIT = 1


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
    G2: routes through canonical I10 intake before persistence. Best-effort idempotency via dedupe_key.
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

        from backend.app.schemas.notification import NotificationPayload
        from backend.app.services.i10.contracts import I10NotificationCandidate
        from backend.app.services.i10.intake import enqueue_i10_notification
        from backend.app.services.i10.policy_types import (
            I10DecisionValue,
            I10NotificationScope,
            I10PrivacyClass,
            I10SemanticFamily,
        )
        from backend.app.services.i10.self_producer_adapter import (
            resolve_or_ensure_self_health_subject_id,
        )

        health_subject_id = resolve_or_ensure_self_health_subject_id(db, user_id)
        # Contract type connection_ping (engagement); presentation type restored post-intake.
        payload = NotificationPayload(
            user_id=user_id,
            type="connection_ping",
            title=title,
            body=body,
            priority="normal",
            scheduled_for=datetime.utcnow(),
            dedupe_key=dedupe_key,
            metadata={
                "language": (lang or "fa")[:20],
                "legacy_producer": "kc_notification",
                "kc_type": _KC_NOTIFICATION_TYPE,
                "candidate_id": candidate_id,
            },
            category="engagement",
            source_type="knowledge_capture",
            source_id=str(candidate_id) if candidate_id is not None else "kc_confirm",
            template_key="kc_confirm",
        )
        candidate = I10NotificationCandidate(
            candidate_key=dedupe_key,
            health_subject_id=health_subject_id,
            recipient_user_id=user_id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
            source_owner="KC_NOTIFY_ADAPTER",
            source_type="kc_confirm_candidate",
            source_id=str(candidate_id) if candidate_id is not None else "none",
            semantic_family=I10SemanticFamily.ENGAGEMENT,
            privacy_hint=I10PrivacyClass.PRIVATE,
        )
        intake = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
        result["attempted"] = True
        if intake.decision != I10DecisionValue.SEND or intake.notification_id is None:
            result["ok"] = True
            result["reason"] = f"i10_{intake.decision.value.lower()}:{intake.reason_code}"
            result["decision_id"] = intake.decision_id
            return result

        notif = (
            db.query(models.Notification)
            .filter(models.Notification.id == intake.notification_id)
            .one()
        )
        # Preserve KC presentation fields without bypassing I10 decision authority.
        notif.type = _KC_NOTIFICATION_TYPE
        notif.channel = _KC_CHANNEL
        notif.language = (lang or "fa")[:20]
        notif.actions_json = '[{"id":"open_chat","type":"OPEN_CHAT"}]'
        if candidate_id is not None:
            notif.deeplink_url = f"sedi://chat?from=kc&candidate_id={candidate_id}"
        elif not notif.deeplink_url:
            notif.deeplink_url = f"sedi://chat?from=notif&id={notif.id}"
        db.add(notif)
        db.commit()
        db.refresh(notif)

        result["ok"] = True
        result["notification_id"] = notif.id
        result["decision_id"] = intake.decision_id

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


def _resolve_lang(lang_query: Optional[str], user: models.User) -> str:
    """Language: query param > user.preferred_language > default 'fa'."""
    if lang_query is not None and (str(lang_query).strip().lower() in ("fa", "en", "en-us", "en-gb")):
        return str(lang_query).strip().lower()
    if user and getattr(user, "preferred_language", None):
        return (str(user.preferred_language).strip().lower() or "fa")[:5]
    return "fa"


@router.get("/next_question", response_model=ApiResponseV1)
def get_next_question_endpoint(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    lang: Optional[str] = Query(None, description="Display language: fa | en"),
    notify: bool = Query(False, description="If true and response is confirm_candidate, send a notification"),
    in_app: bool = Query(False, description="If true with notify=true: create inbox notification only, skip push delivery (user active in app)"),
    db: Session = Depends(get_db),
):
    """
    Get the best next question to ask the authenticated user for proactive data collection.
    Requires Bearer JWT; user identity is derived from the token only.
    """
    user_id = auth_user.id
    user = auth_user
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
    payload: ExtractFromMessageUserRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Extract facts from chat message and create/auto-accept candidates.
    Requires Bearer JWT; user identity is derived from the token only.
    """
    result = process_message(
        db=db,
        user_id=auth_user.id,
        text=payload.text,
        language=payload.language,
        source_message_id=payload.source_message_id,
    )
    return APIResponse(ok=True, data=result, error=None)


@router.post("/apply_answer", response_model=ApiResponseV1)
def apply_answer_endpoint(
    payload: ApplyAnswerUserRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Apply user answer for the authenticated user.
    Requires Bearer JWT; user identity is derived from the token only.
    """
    user_id = auth_user.id
    try:
        raw_value = payload.value
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            if payload.answer is not None and str(payload.answer).strip():
                raw_value = payload.answer

        if payload.candidate_id is not None and (payload.question_type or "").strip().lower() == "confirm_candidate":
            a = payload.answer if (payload.answer is not None and str(payload.answer).strip()) else payload.value
            raw_value = a
        result = apply_answer(
            db=db,
            user_id=user_id,
            field_key=payload.field_key,
            value=raw_value,
            candidate_id=payload.candidate_id,
            question_type=payload.question_type,
        )
        outcome = result.get("outcome")
        if outcome is not None:
            now = datetime.utcnow()
            mark_answer(db, user_id, now, outcome)
            _, _, _, policy_snapshot = check_can_ask(db, user_id, now)
            result = {**result, "policy": policy_snapshot}
        return APIResponse(ok=True, data=result, error=None)
    except (ValueError, TypeError) as e:
        return APIResponse(ok=False, data=None, error=ErrorInfo(code="INVALID_INPUT", message=str(e)))
