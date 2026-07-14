"""
Gate 4C — InteractionEvent service.

Records unified interaction timeline entries. No notifications, GPT, or FCM.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import InteractionEvent, Notification
from backend.app.services.gate4.notification_contract import (
    SmartNotificationAction,
    V1_INTERACTION_CHANNEL,
    normalize_legacy_action,
)

logger = logging.getLogger(__name__)

ALLOWED_INTERACTION_CHANNELS = frozenset({"text", "voice", "call", "video"})
ALLOWED_SOURCES = frozenset({"chat", "notification", "device", "system"})

CANONICAL_ACTION_TO_EVENT_TYPE: Mapping[str, str] = {
    SmartNotificationAction.ACK_THANKS.value: "notification_ack",
    SmartNotificationAction.NOT_NOW.value: "notification_not_now",
    SmartNotificationAction.TALK_LATER.value: "notification_talk_later",
    SmartNotificationAction.OPEN_CHAT.value: "notification_open_chat",
}

LEGACY_EVENT_TYPE_TO_CANONICAL_INPUT: Mapping[str, str] = {
    "like": "like",
    "dislike": "dislike",
    "open": "open",
    "dismiss": "dismiss",
    "open_chat": "open_chat",
}

# Partial unique index name (must match migration 050 + model metadata).
UQ_NOTIF_CHAT_ONCE = "uq_interaction_events_notif_chat_once"


def _serialize_metadata(metadata: Optional[dict[str, Any]]) -> Optional[str]:
    if metadata is None:
        return None
    return json.dumps(metadata, ensure_ascii=False)


def _validate_channel(interaction_channel: str) -> str:
    channel = (interaction_channel or V1_INTERACTION_CHANNEL).strip().lower()
    if channel not in ALLOWED_INTERACTION_CHANNELS:
        raise ValueError(
            f"Invalid interaction_channel: {interaction_channel}. "
            f"Allowed: {sorted(ALLOWED_INTERACTION_CHANNELS)}"
        )
    return channel


def verify_notification_belongs_to_user(
    db: Session,
    *,
    user_id: int,
    notification_id: int,
) -> Notification:
    """Return notification if it exists and belongs to user; else raise LookupError or PermissionError."""
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification is None:
        raise LookupError("Notification not found")
    if notification.user_id != user_id:
        raise PermissionError("Notification does not belong to user")
    return notification


def resolve_canonical_action(
    *,
    action_id: Optional[str],
    legacy_event_type: Optional[str] = None,
) -> str:
    """Resolve Gate 4B canonical action from action_id or legacy feedback event_type."""
    if action_id:
        return normalize_legacy_action(action_id)
    if legacy_event_type:
        legacy_key = legacy_event_type.strip().lower()
        if legacy_key in LEGACY_EVENT_TYPE_TO_CANONICAL_INPUT:
            return normalize_legacy_action(LEGACY_EVENT_TYPE_TO_CANONICAL_INPUT[legacy_key])
        return normalize_legacy_action(legacy_key)
    raise ValueError("action_id or legacy_event_type required")


def event_type_for_canonical_action(
    canonical_action: str,
    *,
    legacy_event_type: Optional[str] = None,
) -> str:
    """Map canonical action to InteractionEvent event_type."""
    if legacy_event_type == "dismiss" and canonical_action == SmartNotificationAction.NOT_NOW.value:
        return "notification_dismiss"
    return CANONICAL_ACTION_TO_EVENT_TYPE.get(canonical_action, "notification_action")


def create_interaction_event(
    db: Session,
    *,
    user_id: int,
    event_type: str,
    source: str,
    interaction_channel: str = V1_INTERACTION_CHANNEL,
    source_notification_id: Optional[int] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str | int] = None,
    conversation_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> InteractionEvent:
    """Persist a single InteractionEvent row."""
    if not event_type or not event_type.strip():
        raise ValueError("event_type is required")
    source_norm = (source or "").strip().lower()
    if source_norm not in ALLOWED_SOURCES:
        raise ValueError(f"Invalid source: {source}. Allowed: {sorted(ALLOWED_SOURCES)}")

    channel = _validate_channel(interaction_channel)
    row = InteractionEvent(
        user_id=user_id,
        event_type=event_type.strip(),
        source=source_norm,
        interaction_channel=channel,
        source_notification_id=source_notification_id,
        source_type=source_type,
        source_id=str(source_id) if source_id is not None else None,
        conversation_id=conversation_id,
        thread_id=thread_id,
        metadata_json=_serialize_metadata(metadata),
    )
    db.add(row)
    db.flush()
    return row


def create_notification_action_event(
    db: Session,
    *,
    user_id: int,
    notification_id: int,
    canonical_action: str,
    legacy_event_type: Optional[str] = None,
    interaction_channel: str = V1_INTERACTION_CHANNEL,
    source_type: Optional[str] = None,
    source_id: Optional[str | int] = None,
    conversation_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> InteractionEvent:
    """Record a notification feedback/action in the interaction timeline."""
    verify_notification_belongs_to_user(db, user_id=user_id, notification_id=notification_id)
    event_type = event_type_for_canonical_action(
        canonical_action,
        legacy_event_type=legacy_event_type,
    )
    meta = dict(metadata or {})
    meta["canonical_action_id"] = canonical_action
    return create_interaction_event(
        db,
        user_id=user_id,
        event_type=event_type,
        source="notification",
        interaction_channel=interaction_channel,
        source_notification_id=notification_id,
        source_type=source_type,
        source_id=source_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        metadata=meta,
    )


def create_notification_action_event_from_feedback(
    db: Session,
    *,
    user_id: int,
    notification_id: int,
    payload: dict[str, Any],
    legacy_event_type: str,
) -> InteractionEvent:
    """Create InteractionEvent from notification feedback payload (canonical or legacy)."""
    notification = verify_notification_belongs_to_user(
        db,
        user_id=user_id,
        notification_id=notification_id,
    )
    canonical = resolve_canonical_action(
        action_id=payload.get("action_id"),
        legacy_event_type=legacy_event_type,
    )
    meta: dict[str, Any] = {}
    if payload.get("reason"):
        meta["reason"] = payload.get("reason")
    if payload.get("reaction"):
        meta["legacy_reaction"] = payload.get("reaction")
    return create_notification_action_event(
        db,
        user_id=user_id,
        notification_id=notification_id,
        canonical_action=canonical,
        legacy_event_type=legacy_event_type,
        source_type=notification.source_type,
        source_id=notification.source_id,
        metadata=meta or None,
    )


def create_notification_open_chat_event(
    db: Session,
    *,
    user_id: int,
    notification_id: int,
    conversation_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> InteractionEvent:
    """Record OPEN_CHAT / notification_open_chat interaction."""
    return create_notification_action_event(
        db,
        user_id=user_id,
        notification_id=notification_id,
        canonical_action=SmartNotificationAction.OPEN_CHAT.value,
        conversation_id=conversation_id,
        thread_id=thread_id,
        metadata=metadata,
    )


def _normalized_conversation_id(conversation_id: Optional[str]) -> Optional[str]:
    if conversation_id is None:
        return None
    stripped = conversation_id.strip()
    return stripped if stripped else None


def find_existing_notification_chat_message_event(
    db: Session,
    *,
    user_id: int,
    source_notification_id: int,
    conversation_id: Optional[str] = None,
) -> Optional[InteractionEvent]:
    """
    Return earliest notification-linked chat_message event for this owner+source.

    ``conversation_id`` is accepted for call-site compatibility but is NOT part of
    the consumption identity (Section 15 B8 invariant).
    """
    _ = conversation_id  # intentionally unused for matching
    return (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user_id,
            InteractionEvent.source_notification_id == source_notification_id,
            InteractionEvent.event_type == "chat_message",
        )
        .order_by(InteractionEvent.id.asc())
        .first()
    )


def _is_notif_chat_once_integrity_error(exc: IntegrityError) -> bool:
    """True only for the B8 partial unique index (not unrelated constraints)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == UQ_NOTIF_CHAT_ONCE:
        return True
    # SQLite / drivers without diag.constraint_name: safe fallback string match.
    text_blob = " ".join(
        str(part)
        for part in (exc, orig, diag, constraint_name)
        if part is not None
    ).lower()
    return UQ_NOTIF_CHAT_ONCE.lower() in text_blob or (
        "interaction_events" in text_blob
        and "source_notification_id" in text_blob
        and ("unique" in text_blob or "duplicate" in text_blob)
    )


def create_chat_message_event(
    db: Session,
    *,
    user_id: int,
    source_notification_id: Optional[int] = None,
    conversation_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    interaction_source: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> InteractionEvent:
    """
    Record a chat message continuation event.

    When source_notification_id is set, verifies notification ownership and
    enforces one-consumption-per-(user, source_notification) via select-before-insert
    plus DB partial unique index conflict recovery (savepoint).
    """
    source = "notification" if source_notification_id is not None else "chat"
    if interaction_source:
        candidate = interaction_source.strip().lower()
        if candidate in ALLOWED_SOURCES:
            source = candidate

    normalized_conversation_id = _normalized_conversation_id(conversation_id)

    if source_notification_id is not None:
        notification = verify_notification_belongs_to_user(
            db,
            user_id=user_id,
            notification_id=source_notification_id,
        )
        existing = find_existing_notification_chat_message_event(
            db,
            user_id=user_id,
            source_notification_id=source_notification_id,
        )
        if existing is not None:
            return existing
    else:
        notification = None

    meta = dict(metadata or {})
    if source_notification_id is not None:
        meta["continued_from_notification"] = True

    def _insert() -> InteractionEvent:
        return create_interaction_event(
            db,
            user_id=user_id,
            event_type="chat_message",
            source=source,
            interaction_channel=V1_INTERACTION_CHANNEL,
            source_notification_id=source_notification_id,
            source_type=notification.source_type if notification else None,
            source_id=notification.source_id if notification else None,
            conversation_id=normalized_conversation_id,
            thread_id=thread_id,
            metadata=meta or None,
        )

    if source_notification_id is None:
        return _insert()

    try:
        with db.begin_nested():
            return _insert()
    except IntegrityError as exc:
        if not _is_notif_chat_once_integrity_error(exc):
            raise
        recovered = find_existing_notification_chat_message_event(
            db,
            user_id=user_id,
            source_notification_id=source_notification_id,
        )
        if recovered is None:
            raise
        logger.info(
            "[GATE4C] notif chat_message idempotent collision user_id=%s source_notification_id=%s existing_id=%s",
            user_id,
            source_notification_id,
            recovered.id,
        )
        return recovered
