"""I10-B12 contextual follow-up notification adapter — structured CareFollowUpTask only."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    sanitize_notification_context,
)
from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta
from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i10.self_producer_adapter import resolve_or_ensure_self_health_subject_id

logger = logging.getLogger(__name__)

FOLLOWUP_PRODUCER_OWNER = "I10_CONTEXTUAL_FOLLOWUP"


def build_followup_occurrence_key(*, task_id: int) -> str:
    return f"i10:self:followup:{task_id}"


def resolve_semantic_family(task: models.CareFollowUpTask) -> I10SemanticFamily:
    if task.source == FollowUpTaskSource.POST_EVENT.value:
        return I10SemanticFamily.POST_EVENT_FOLLOW_UP
    return I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP


def resolve_privacy_class(task: models.CareFollowUpTask) -> I10PrivacyClass:
    if task.source == FollowUpTaskSource.POST_EVENT.value:
        return I10PrivacyClass.HEALTH_SENSITIVE
    return I10PrivacyClass.PRIVATE


def _safe_user_name(db: Session, user_id: int) -> Optional[str]:
    row = db.query(models.User.name).filter(models.User.id == user_id).first()
    if not row or not row[0]:
        return None
    return str(row[0]).strip()[:64] or None


def _care_checkin_copy(db: Session, task: models.CareFollowUpTask, name: Optional[str]) -> tuple[str, str, str]:
    """R-018: lock-screen-safe, warm check-in. Never names the event (loss, job, surgery...) — only that Sedi is thinking of them."""
    lang = "fa"
    try:
        row = db.query(models.User.preferred_language).filter(models.User.id == task.user_id).first()
        raw = ((row[0] if row else None) or "fa").strip().lower().split("-")[0]
        lang = raw if raw in ("fa", "en", "ar") else "en"
    except Exception:
        pass
    if lang == "fa":
        who = f"{name} جان، " if name else ""
        return "صدی", f"{who}دلم خواست حالت رو بپرسم. هر وقت وقت داشتی بیا کمی با هم حرف بزنیم؛ من اینجام.", "care_checkin"
    if lang == "ar":
        who = f"{name}، " if name else ""
        return "صدی", f"{who}أحببت أن أطمئن عليك. تعال نتحدث قليلاً عندما يناسبك؛ أنا هنا.", "care_checkin"
    who = f"{name}, " if name else ""
    return "Sedi", f"{who}I wanted to check in on you. Come talk for a bit whenever you have time; I'm here.", "care_checkin"


_INITIATIVE_COPY = {
    "mood": {
        "fa": "{who}امروز حالت چطوره؟ هر چی تو دلته بگو، من گوش می‌دم.",
        "en": "{who}how are you today? Tell me whatever is on your heart, I am listening.",
        "ar": "{who}كيف حالك اليوم؟ قل ما في قلبك، أنا أُصغي.",
    },
    "suggestion": {
        "fa": "{who}راستی، اون پیشنهادی که دادم چطور پیش رفت؟ دلم می‌خواد بدونم.",
        "en": "{who}how did that suggestion of mine go? I would love to know.",
        "ar": "{who}كيف سار اقتراحي الذي قدّمته؟ أحب أن أعرف.",
    },
    "health": {
        "fa": "{who}یه سر زدم ببینم امروز بدن و حالت چطوره؛ اگه خواستی با هم یه کار کوچیک برای مراقبت از خودت انجام بدیم.",
        "en": "{who}I stopped by to see how your body and mood are today; if you like, let us do one small thing to look after you.",
        "ar": "{who}مررت لأطمئن على جسدك ومزاجك اليوم؛ إن أردت نقوم بشيء صغير للعناية بك.",
    },
}


def _initiative_copy(db: Session, task: models.CareFollowUpTask, name: Optional[str]) -> tuple[str, str, str]:
    """R-021 / M5: warm, lock-screen-safe daily initiative (never names a condition or a cause)."""
    kind = str(task.title or "").split(":", 1)[-1].strip()
    kind = kind if kind in _INITIATIVE_COPY else "mood"
    lang = "fa"
    try:
        row = db.query(models.User.preferred_language).filter(models.User.id == task.user_id).first()
        raw = ((row[0] if row else None) or "fa").strip().lower().split("-")[0]
        lang = raw if raw in ("fa", "en", "ar") else "en"
    except Exception:
        pass
    who = (f"{name} جان، " if lang == "fa" else f"{name}, ") if name else ""
    body = _INITIATIVE_COPY[kind][lang].format(who=who)
    if lang == "en" and not who:
        body = body[:1].upper() + body[1:]
    return ("Sedi" if lang == "en" else "صدی"), body, "daily_initiative"


def _explicit_language(db: Session, user_id: int) -> str:
    """fa/ar only when the user's language is explicitly set; otherwise the long-standing English copy stays."""
    try:
        row = db.query(models.User.preferred_language).filter(models.User.id == user_id).first()
        raw = ((row[0] if row else None) or "").strip().lower().split("-")[0]
        return raw if raw in ("fa", "ar") else "en"
    except Exception:
        return "en"


def _reaction_hints(db: Session, user_id: int) -> dict:
    """P7: what Sedi learned from the user's Like/Dislike/dismiss reactions (content hints). Fail-open."""
    try:
        from datetime import datetime

        from backend.app.services.notifications.adaptive_policy_v1 import compute_adaptive_state

        return compute_adaptive_state(db, user_id, datetime.utcnow()).get("content_hints") or {}
    except Exception:
        return {}


_GENERAL_FOLLOWUP = {
    # (with the topic) / (gentle: the user said the last follow-up was not relevant, unclear or too much)
    "fa": (
        "{who}گفته بودی بعداً درباره‌ی «{topic}» ادامه بدیم. الان وقت داری؟",
        "{who}دلم خواست ادامه‌ی حرف‌هامون رو بگیریم. هر وقت وقت داشتی، من اینجام.",
    ),
    "ar": (
        "{who}طلبتَ أن نكمل لاحقاً حديثنا عن «{topic}». هل لديك وقت الآن؟",
        "{who}أحببت أن نكمل حديثنا. في أي وقت يناسبك، أنا هنا.",
    ),
}
_POST_EVENT_FOLLOWUP = {
    "fa": "{who}موعدت چطور پیش رفت؟ اگه خواستی درباره‌اش حرف بزنیم.",
    "ar": "{who}كيف سار موعدك؟ إن أردت نتحدث عنه.",
}


def render_followup_copy(
    db: Session,
    task: models.CareFollowUpTask,
) -> tuple[str, str, str]:
    """Deterministic bounded copy — no attendance claims, no invented health facts."""
    _user_text, meta = parse_bounded_meta(task.description)
    name = _safe_user_name(db, task.user_id)
    prefix = f"{name}, " if name else ""

    if meta.follow_up_kind == "care_checkin":
        return _care_checkin_copy(db, task, name)
    if meta.follow_up_kind == "daily_initiative":
        return _initiative_copy(db, task, name)

    # P7: the follow-up speaks the user's language, and learns from reactions - a user who said the last one was not
    # relevant / unclear gets the gentle wording without the topic.
    lang = _explicit_language(db, task.user_id)
    if lang in ("fa", "ar"):
        hints = _reaction_hints(db, task.user_id)
        who = (f"{name} جان، " if lang == "fa" else f"{name}، ") if name else ""
        if task.source == FollowUpTaskSource.POST_EVENT.value:
            return "صدی", _POST_EVENT_FOLLOWUP[lang].format(who=who), "post_event_follow_up"
        with_topic, gentle = _GENERAL_FOLLOWUP[lang]
        topic = (task.title or "").strip()[:120]
        use_gentle = (
            not topic
            or hints.get("avoid_topic")
            or hints.get("simple_copy")
            or hints.get("lighter_touch")
        )
        body = gentle.format(who=who) if use_gentle else with_topic.format(who=who, topic=topic)
        return "صدی", body, "contextual_follow_up"

    if task.source == FollowUpTaskSource.POST_EVENT.value:
        title = "Follow-up on your appointment"
        body = (
            f"{prefix}how did your appointment go? "
            "If you'd like, we can talk about it."
        )
        template_key = "post_event_follow_up"
    else:
        title = "Continuing our conversation"
        topic = (task.title or "this topic").strip()[:120]
        body = (
            f"{prefix}you asked to continue later about '{topic}'. "
            "Do you have time to talk now?"
        )
        template_key = "contextual_follow_up"

    if meta.follow_up_kind == "general_ctx" and task.source == FollowUpTaskSource.MANUAL.value:
        body = (
            f"{prefix}you asked to follow up later about '{task.title[:120]}'. "
            "Do you have time now?"
        )

    return title, body, template_key


def build_followup_payload(
    db: Session,
    task: models.CareFollowUpTask,
    *,
    occurrence_key: str,
) -> NotificationPayload:
    title, body, template_key = render_followup_copy(db, task)
    _user_text, meta = parse_bounded_meta(task.description)
    context = sanitize_notification_context(
        {
            "template_key": template_key,
            "trigger_reason": "contextual_follow_up",
            "source_summary_key": f"follow_up_task:{task.id}",
            "action_hint": task.source,
        }
    )
    notif_type = "connection_ping"
    if task.source == FollowUpTaskSource.POST_EVENT.value:
        notif_type = "health_alert"
    return NotificationPayload(
        user_id=task.user_id,
        type=notif_type,
        title=title,
        body=body,
        priority="normal",
        dedupe_key=occurrence_key,
        metadata={
            "alert_code": "contextual_follow_up",
            "follow_up_task_id": task.id,
            "follow_up_source": task.source,
            "follow_up_kind": meta.follow_up_kind,
            "user_event_id": meta.user_event_id,
            "prior_source_notification_id": meta.source_notification_id,
        },
        category=NotificationCategory.CARE_FOLLOW_UP.value,
        source_type=NotificationSourceType.CARE_FOLLOW_UP_TASK.value,
        source_id=str(task.id),
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key=template_key,
        context=context,
        privacy_class=resolve_privacy_class(task).value,
    )


def enqueue_contextual_followup_notification(
    db: Session,
    *,
    task: models.CareFollowUpTask,
) -> Optional[models.Notification]:
    occurrence_key = build_followup_occurrence_key(task_id=task.id)
    health_subject_id = resolve_or_ensure_self_health_subject_id(db, task.user_id)
    payload = build_followup_payload(db, task, occurrence_key=occurrence_key)
    semantic = resolve_semantic_family(task)
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=task.user_id,
        notification_scope=I10NotificationScope.CARE_ACTION,
        source_owner=FOLLOWUP_PRODUCER_OWNER,
        source_type="contextual_followup_worker",
        source_id=str(task.id),
        semantic_family=semantic,
        privacy_hint=resolve_privacy_class(task),
        provenance_refs=(f"care_follow_up_task:{task.id}", f"source:{task.source}"),
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B12] suppressed user=%s task=%s reason=%s",
            task.user_id,
            task.id,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
