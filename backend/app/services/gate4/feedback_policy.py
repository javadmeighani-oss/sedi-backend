"""Gate 4D-6 — Feedback suppress/defer and active-conversation helpers."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.models import InteractionEvent, Notification, NotificationGuardState
from backend.app.services.gate4.feature_flags import (
    gate4_active_conversation_defer_enabled,
    gate4_feedback_policy_enabled,
)
from backend.app.services.gate4.notification_contract import (
    NOT_NOW_SUPPRESS_HOURS,
    TALK_LATER_DEFER_HOURS,
    SmartNotificationAction,
    SmartNotificationRisk,
)
from backend.app.services.gate4.notification_policy import NotificationPolicyDecision

logger = logging.getLogger(__name__)

_TYPE_TO_CATEGORY: dict[str, str] = {
    "morning_brief": "daily",
    "connection_ping": "engagement",
    "health_alert": "health_alert",
    "device_disconnected": "device",
    "companion_ping": "companion",
}


def _category_from_notification_type(notification_type: str) -> str:
    return _TYPE_TO_CATEGORY.get((notification_type or "").strip().lower(), "system")

ACTIVE_CONVERSATION_WINDOW_MINUTES = 15
ACTIVE_CONVERSATION_DEFER_MINUTES = 15

ACTIVE_CONVERSATION_EVENT_TYPES = frozenset(
    {
        "chat_message",
        "notification_open_chat",
    }
)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_naive_utc(dt: datetime) -> datetime:
    return _ensure_utc(dt).replace(tzinfo=None)


def _normalize_channel(channel: Optional[str], notification: Any = None) -> str:
    if channel:
        return str(channel).strip().lower()[:50]
    if notification is not None:
        notif_channel = getattr(notification, "channel", None)
        if notif_channel:
            return str(notif_channel).strip().lower()[:50]
        notif_type = getattr(notification, "type", None)
        if notif_type:
            return _category_from_notification_type(str(notif_type))[:50]
    return "push"


def _scope_key(
    *,
    template_key: Optional[str] = None,
    category: Optional[str] = None,
    notification: Any = None,
) -> str:
    if template_key:
        return str(template_key).strip().lower()[:40]
    if category:
        return str(category).strip().lower()[:40]
    if notification is not None:
        return _category_from_notification_type(getattr(notification, "type", None) or "")[:40]
    return "system"


def build_feedback_rule_id(action_prefix: str, channel: str, scope: str) -> str:
    """Build Gate 4 feedback guard rule_id (max 100 chars)."""
    rule_id = f"gate4:{action_prefix}:{channel}:{scope}"
    return rule_id[:100]


def _upsert_guard_cooldown(
    db: Session,
    *,
    user_id: int,
    channel: str,
    rule_id: str,
    cooldown_until: datetime,
    now_utc: datetime,
) -> NotificationGuardState:
    now_naive = _to_naive_utc(now_utc)
    cooldown_naive = _to_naive_utc(cooldown_until)
    row = (
        db.query(NotificationGuardState)
        .filter(
            NotificationGuardState.user_id == user_id,
            NotificationGuardState.channel == channel,
            NotificationGuardState.rule_id == rule_id,
        )
        .one_or_none()
    )
    if row is None:
        row = NotificationGuardState(
            user_id=user_id,
            channel=channel,
            rule_id=rule_id,
            last_sent_at=now_naive,
            cooldown_until=cooldown_naive,
            updated_at=now_naive,
        )
        db.add(row)
    else:
        row.last_sent_at = now_naive
        row.cooldown_until = cooldown_naive
        row.updated_at = now_naive
    db.flush()
    return row


def is_user_active_conversation(
    db: Session,
    *,
    user_id: int,
    now_utc: datetime | None = None,
    window_minutes: int = ACTIVE_CONVERSATION_WINDOW_MINUTES,
) -> bool:
    """True when user has chat_message or notification_open_chat within window."""
    effective_now = _to_naive_utc(now_utc or datetime.now(timezone.utc))
    cutoff = effective_now - timedelta(minutes=max(window_minutes, 0))
    row = (
        db.query(InteractionEvent.id)
        .filter(
            InteractionEvent.user_id == user_id,
            InteractionEvent.event_type.in_(tuple(ACTIVE_CONVERSATION_EVENT_TYPES)),
            InteractionEvent.created_at >= cutoff,
        )
        .order_by(InteractionEvent.created_at.desc())
        .first()
    )
    return row is not None


def get_feedback_policy_block(
    db: Session,
    *,
    user_id: int,
    channel: str,
    template_key: Optional[str] = None,
    category: Optional[str] = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """
    Return active feedback suppress/defer state for a channel+scope.

    Returns dict with keys: blocked, block_type (suppress|defer|None), cooldown_until, reason, rule_id.
    """
    if not gate4_feedback_policy_enabled():
        return {
            "blocked": False,
            "block_type": None,
            "cooldown_until": None,
            "reason": None,
            "rule_id": None,
        }

    effective_now = _to_naive_utc(now_utc or datetime.now(timezone.utc))
    scope = _scope_key(template_key=template_key, category=category)
    channel_norm = _normalize_channel(channel)

    for action_prefix, block_type in (
        ("not_now", "suppress"),
        ("talk_later", "defer"),
    ):
        rule_id = build_feedback_rule_id(action_prefix, channel_norm, scope)
        row = (
            db.query(NotificationGuardState)
            .filter(
                NotificationGuardState.user_id == user_id,
                NotificationGuardState.channel == channel_norm,
                NotificationGuardState.rule_id == rule_id,
            )
            .one_or_none()
        )
        if row is None or row.cooldown_until is None:
            continue
        if row.cooldown_until > effective_now:
            return {
                "blocked": True,
                "block_type": block_type,
                "cooldown_until": row.cooldown_until,
                "reason": f"feedback_{block_type}",
                "rule_id": rule_id,
            }

    return {
        "blocked": False,
        "block_type": None,
        "cooldown_until": None,
        "reason": None,
        "rule_id": None,
    }


def apply_feedback_policy(
    db: Session,
    *,
    user_id: int,
    notification: Notification,
    canonical_action: str,
    now_utc: datetime | None = None,
    template_key: Optional[str] = None,
    category: Optional[str] = None,
) -> dict[str, Any]:
    """
    Apply Gate 4 feedback policy (NotificationGuardState). No FCM.

    Caller must commit the session. Returns a safe summary dict for optional API metadata.
    """
    if not gate4_feedback_policy_enabled():
        return {"applied": False, "reason": "flag_off"}

    effective_now = _ensure_utc(now_utc or datetime.now(timezone.utc))
    channel = _normalize_channel(None, notification)
    scope = _scope_key(template_key=template_key, category=category, notification=notification)
    action = (canonical_action or "").strip().upper()

    result: dict[str, Any] = {
        "applied": True,
        "canonical_action": action,
        "channel": channel,
        "scope": scope,
        "guard_updated": False,
        "rule_id": None,
        "cooldown_until": None,
    }

    if action == SmartNotificationAction.ACK_THANKS.value:
        rule_id = build_feedback_rule_id("ack", channel, scope)
        _upsert_guard_cooldown(
            db,
            user_id=user_id,
            channel=channel,
            rule_id=rule_id,
            cooldown_until=_to_naive_utc(effective_now),
            now_utc=effective_now,
        )
        result["guard_updated"] = True
        result["rule_id"] = rule_id
        return result

    if action == SmartNotificationAction.NOT_NOW.value:
        rule_id = build_feedback_rule_id("not_now", channel, scope)
        until = effective_now + timedelta(hours=NOT_NOW_SUPPRESS_HOURS)
        _upsert_guard_cooldown(
            db,
            user_id=user_id,
            channel=channel,
            rule_id=rule_id,
            cooldown_until=until,
            now_utc=effective_now,
        )
        result["guard_updated"] = True
        result["rule_id"] = rule_id
        result["cooldown_until"] = _to_naive_utc(until).isoformat()
        result["suppress_hours"] = NOT_NOW_SUPPRESS_HOURS
        return result

    if action == SmartNotificationAction.TALK_LATER.value:
        rule_id = build_feedback_rule_id("talk_later", channel, scope)
        until = effective_now + timedelta(hours=TALK_LATER_DEFER_HOURS)
        _upsert_guard_cooldown(
            db,
            user_id=user_id,
            channel=channel,
            rule_id=rule_id,
            cooldown_until=until,
            now_utc=effective_now,
        )
        result["guard_updated"] = True
        result["rule_id"] = rule_id
        result["cooldown_until"] = _to_naive_utc(until).isoformat()
        result["defer_hours"] = TALK_LATER_DEFER_HOURS
        return result

    if action == SmartNotificationAction.OPEN_CHAT.value:
        result["guard_updated"] = False
        result["note"] = "open_chat_uses_interaction_event_for_active_conversation"
        return result

    result["applied"] = False
    result["reason"] = "unsupported_action"
    return result


def augment_policy_decision_with_gate4d6(
    db: Session,
    *,
    user_id: int,
    risk: str,
    category: str,
    channel: str,
    decision: NotificationPolicyDecision,
    now_utc: datetime,
    template_key: Optional[str] = None,
) -> NotificationPolicyDecision:
    """
    Overlay feedback suppress/defer and active-conversation defer on a policy decision.

    No-op when flags are off. Critical risk is never suppressed/deferred.
    """
    if not gate4_feedback_policy_enabled() and not gate4_active_conversation_defer_enabled():
        return decision

    normalized_risk = (risk or "").strip().lower()
    if normalized_risk == SmartNotificationRisk.CRITICAL.value:
        return decision

    effective_now = _ensure_utc(now_utc)
    updated = decision

    if gate4_feedback_policy_enabled():
        block = get_feedback_policy_block(
            db,
            user_id=user_id,
            channel=channel,
            template_key=template_key,
            category=category,
            now_utc=effective_now,
        )
        if block.get("blocked"):
            cooldown = block.get("cooldown_until")
            defer_until = None
            if cooldown is not None and isinstance(cooldown, datetime):
                defer_until = (
                    cooldown.replace(tzinfo=timezone.utc)
                    if cooldown.tzinfo is None
                    else _ensure_utc(cooldown)
                )
            if block.get("block_type") == "suppress":
                updated = replace(
                    updated,
                    action="suppress",
                    reason="feedback_suppressed",
                    defer_until=defer_until,
                )
            elif block.get("block_type") == "defer":
                updated = replace(
                    updated,
                    action="defer",
                    reason="feedback_deferred",
                    defer_until=defer_until or (effective_now + timedelta(hours=TALK_LATER_DEFER_HOURS)),
                )

    if gate4_active_conversation_defer_enabled():
        if is_user_active_conversation(db, user_id=user_id, now_utc=effective_now):
            if updated.action == "allow":
                updated = replace(
                    updated,
                    action="defer",
                    reason="active_conversation",
                    defer_until=effective_now + timedelta(minutes=ACTIVE_CONVERSATION_DEFER_MINUTES),
                )

    return updated
