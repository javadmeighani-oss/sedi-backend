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
from backend.app import sedi_copy

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
    who = sedi_copy.t("address.followup", lang, name=name) if name else ""
    return (
        sedi_copy.t("followup.title.brand", lang),
        sedi_copy.t("followup.care_checkin.body", lang, who=who),
        "care_checkin",
    )


_INITIATIVE_COPY = sedi_copy.nested_by_lang("followup.initiative")


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
    who = sedi_copy.t("address.initiative", lang, name=name) if name else ""
    body = _INITIATIVE_COPY[kind][lang].format(who=who)
    if lang == "en" and not who:
        body = body[:1].upper() + body[1:]
    return sedi_copy.t("followup.title.brand", lang), body, "daily_initiative"


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


_GENERAL_FOLLOWUP = sedi_copy.by_lang("followup.general")
_POST_EVENT_FOLLOWUP = sedi_copy.by_lang("followup.post_event")


def render_followup_copy(
    db: Session,
    task: models.CareFollowUpTask,
) -> tuple[str, str, str]:
    """Deterministic bounded copy — no attendance claims, no invented health facts."""
    _user_text, meta = parse_bounded_meta(task.description)
    name = _safe_user_name(db, task.user_id)
    prefix = sedi_copy.t("address.followup", "en", name=name) if name else ""

    if meta.follow_up_kind == "care_checkin":
        return _care_checkin_copy(db, task, name)
    if meta.follow_up_kind == "daily_initiative":
        return _initiative_copy(db, task, name)

    # P7: the follow-up speaks the user's language, and learns from reactions - a user who said the last one was not
    # relevant / unclear gets the gentle wording without the topic.
    lang = _explicit_language(db, task.user_id)
    if lang in ("fa", "ar"):
        hints = _reaction_hints(db, task.user_id)
        who = sedi_copy.t("address.followup", lang, name=name) if name else ""
        if task.source == FollowUpTaskSource.POST_EVENT.value:
            return sedi_copy.t("followup.title.post_event", lang), _POST_EVENT_FOLLOWUP[lang].format(who=who), "post_event_follow_up"
        with_topic, gentle = _GENERAL_FOLLOWUP[lang]
        topic = (task.title or "").strip()[:120]
        use_gentle = (
            not topic
            or hints.get("avoid_topic")
            or hints.get("simple_copy")
            or hints.get("lighter_touch")
        )
        body = gentle.format(who=who) if use_gentle else with_topic.format(who=who, topic=topic)
        return sedi_copy.t("followup.title.general", lang), body, "contextual_follow_up"

    if task.source == FollowUpTaskSource.POST_EVENT.value:
        title = sedi_copy.t("followup.title.post_event", "en")
        body = _POST_EVENT_FOLLOWUP["en"].format(who=prefix)
        template_key = "post_event_follow_up"
    else:
        title = sedi_copy.t("followup.title.general", "en")
        topic = (task.title or "this topic").strip()[:120]
        body = _GENERAL_FOLLOWUP["en"][0].format(who=prefix, topic=topic)
        template_key = "contextual_follow_up"

    if meta.follow_up_kind == "general_ctx" and task.source == FollowUpTaskSource.MANUAL.value:
        body = _GENERAL_FOLLOWUP["en"][1].format(who=prefix, topic=task.title[:120])

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
