"""I10-B17 — domain-safe notification interaction recorder (ledger-only by default)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models import InteractionEvent, Memory, Notification, NotificationFeedback
from backend.app.services.gate4.interaction_event_service import create_interaction_event
from backend.app.services.i10.interaction_vocabulary import (
    VOCABULARY_VERSION,
    CanonicalInteractionVerb,
    event_type_for_verb,
    resolve_interaction_verb,
    assert_generic_verb_cannot_complete_domain,
)

_log = logging.getLogger(__name__)

# Notification presence evidence only — NOT I7 personal-memory authority.
NOTIFICATION_PRESENCE_EVENT_TYPES = frozenset(
    {
        "notification_like",
        "notification_dislike",
        "notification_dislike_reason",
        "notification_open_chat",
    }
)


@dataclass(frozen=True)
class InteractionRecordResult:
    feedback_id: Optional[int]
    interaction_event_id: int
    canonical_verb: str
    event_type: str
    gate4_feedback_summary: Optional[dict[str, Any]]


def _bounded_feedback_meta(
    payload: dict[str, Any],
    resolved,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "canonical_verb": resolved.verb.value,
        "vocabulary_version": VOCABULARY_VERSION,
    }
    if resolved.reason:
        meta["reason"] = resolved.reason
        meta["dislike_reason_bounded"] = resolved.dislike_reason_bounded
    feedback_text = payload.get("feedback_text")
    if feedback_text is not None:
        meta["feedback_text"] = str(feedback_text)[:256]
    timestamp = payload.get("timestamp") or payload.get("client_ts")
    if timestamp:
        meta["client_timestamp"] = timestamp
    action_id = payload.get("action_id")
    if action_id:
        meta["action_id"] = action_id
    if payload.get("reaction"):
        meta["legacy_reaction"] = payload.get("reaction")
    if payload.get("meta"):
        meta["legacy_meta"] = payload.get("meta")
    return meta


def _apply_gate4_policy(
    db: Session,
    *,
    user_id: int,
    notification: Notification,
    canonical_action: str,
) -> Optional[dict[str, Any]]:
    try:
        from backend.app.services.gate4.feedback_policy import apply_feedback_policy

        return apply_feedback_policy(
            db,
            user_id=user_id,
            notification=notification,
            canonical_action=canonical_action,
            template_key=getattr(notification, "template_key", None),
            category=getattr(notification, "category", None),
        )
    except Exception:
        _log.exception(
            "[I10-B17] feedback_policy_failed notification_id=%s user_id=%s",
            notification.id,
            user_id,
        )
        return None


def record_notification_interaction(
    db: Session,
    *,
    notification: Notification,
    recipient_user_id: int,
    payload: dict[str, Any],
    domain_completion_authorized: bool = False,
) -> InteractionRecordResult:
    """
    Persist NotificationFeedback + InteractionEvent without domain mutation.

    Domain completion (medication taken, I8 action completed, etc.) remains on
    authorized source-domain endpoints only. Pass domain_completion_authorized=True
    only after an I8-owned (or other domain-owner) completion command has succeeded.
    """
    resolved = resolve_interaction_verb(payload)
    if resolved.verb is CanonicalInteractionVerb.DONE:
        if not domain_completion_authorized:
            raise HTTPException(
                status_code=422,
                detail="DONE requires an authorized domain completion endpoint.",
            )
    else:
        try:
            assert_generic_verb_cannot_complete_domain(notification, resolved.verb)
        except ValueError as exc:
            if str(exc) == "done_requires_domain_authority":
                raise HTTPException(
                    status_code=422,
                    detail="DONE requires an authorized domain completion endpoint.",
                ) from exc
            raise

    meta = _bounded_feedback_meta(payload, resolved)
    if domain_completion_authorized and resolved.verb is CanonicalInteractionVerb.DONE:
        meta["domain_completion_authorized"] = True
        meta["completion_authority"] = "I8_OPERATIONAL_PLAN_ACTION_DOMAIN"
    feedback_row = NotificationFeedback(
        notification_id=notification.id,
        user_id=recipient_user_id,
        action=resolved.feedback_action,
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    db.add(feedback_row)
    db.flush()

    event_meta = dict(meta)
    event = create_interaction_event(
        db,
        user_id=recipient_user_id,
        event_type=event_type_for_verb(resolved.verb),
        source="notification",
        source_notification_id=notification.id,
        source_type=notification.source_type,
        source_id=notification.source_id,
        metadata=event_meta,
    )

    gate4_summary = None
    if resolved.gate4_policy_action:
        gate4_summary = _apply_gate4_policy(

            db,
            user_id=recipient_user_id,
            notification=notification,
            canonical_action=resolved.gate4_policy_action,
        )

    return InteractionRecordResult(
        feedback_id=feedback_row.id,
        interaction_event_id=event.id,
        canonical_verb=resolved.verb.value,
        event_type=event.event_type,
        gate4_feedback_summary=gate4_summary,
    )


def record_notification_read(
    db: Session,
    *,
    notification: Notification,
    recipient_user_id: int,
) -> Optional[InteractionRecordResult]:
    """Mark notification read and record a single READ interaction event on first transition."""
    was_unread = not notification.is_read
    notification.is_read = True
    if not was_unread:
        return None

    payload: dict[str, Any] = {"reaction": "seen"}
    resolved = resolve_interaction_verb(payload)
    event_meta = {
        "canonical_verb": resolved.verb.value,
        "vocabulary_version": VOCABULARY_VERSION,
        "legacy_reaction": "seen",
    }
    event = create_interaction_event(
        db,
        user_id=recipient_user_id,
        event_type=event_type_for_verb(CanonicalInteractionVerb.READ),
        source="notification",
        source_notification_id=notification.id,
        source_type=notification.source_type,
        source_id=notification.source_id,
        metadata=event_meta,
    )
    return InteractionRecordResult(
        feedback_id=None,
        interaction_event_id=event.id,
        canonical_verb=resolved.verb.value,
        event_type=event.event_type,
        gate4_feedback_summary=None,
    )


def latest_interaction_event_for_notification(
    db: Session,
    *,
    notification_id: int,
) -> Optional[InteractionEvent]:
    return (
        db.query(InteractionEvent)
        .filter(InteractionEvent.source_notification_id == notification_id)
        .order_by(InteractionEvent.id.desc())
        .first()
    )


def get_last_chat_activity_at(db: Session, user_id: int) -> Optional[datetime]:
    """CHAT_ACTIVITY — last conversational Memory turn (not notification presence)."""
    row = (
        db.query(Memory.created_at)
        .filter(Memory.user_id == user_id)
        .order_by(Memory.created_at.desc())
        .first()
    )
    return row[0] if row else None


def get_last_notification_presence_at(db: Session, user_id: int) -> Optional[datetime]:
    """NOTIFICATION_PRESENCE_ACTIVITY from existing InteractionEvent ledger only."""
    row = (
        db.query(InteractionEvent.created_at)
        .filter(
            InteractionEvent.user_id == user_id,
            InteractionEvent.event_type.in_(tuple(NOTIFICATION_PRESENCE_EVENT_TYPES)),
        )
        .order_by(InteractionEvent.created_at.desc())
        .first()
    )
    return row[0] if row else None


def get_last_user_presence_at(db: Session, user_id: int) -> Optional[datetime]:
    """
    Latest trustworthy presence baseline for reengagement eligibility.

    Uses only existing persisted evidence:
    - chat Memory timestamps
    - notification LIKE / DISLIKE / OPEN_CHAT InteractionEvent timestamps

    Does not invent baselines, does not promote presence into I7 memory authority,
    and does not treat account creation alone as meaningful presence.
    """
    candidates = [
        ts
        for ts in (
            get_last_chat_activity_at(db, user_id),
            get_last_notification_presence_at(db, user_id),
        )
        if ts is not None
    ]
    if not candidates:
        return None
    return max(candidates)


def is_eligible_for_presence_reengagement(
    db: Session,
    user_id: int,
    *,
    when: datetime,
    inactive_hours: int = 4,
) -> bool:
    """Fail-closed eligibility: requires a real presence baseline and idle >= threshold."""
    last = get_last_user_presence_at(db, user_id)
    if last is None:
        return False
    return (when - last) >= timedelta(hours=inactive_hours)


def has_recent_engagement_family_notification(
    db: Session,
    *,
    user_id: int,
    since: datetime,
) -> bool:
    """True when PRESENCE_REENGAGEMENT or ENGAGEMENT_NUDGE sibling exists after cutoff (exclusive).

    Prefer scheduled_for when present so cooldown aligns with producer occurrence time
    (not wall-clock created_at), which keeps later occurrences at +4h valid.
    """
    from sqlalchemy import and_, or_

    from backend.app.models import Notification
    from backend.app.services.i10.policy_types import I10SemanticFamily

    family_filter = or_(
        Notification.semantic_family.in_(
            (
                I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
                I10SemanticFamily.ENGAGEMENT_NUDGE.value,
            )
        ),
        Notification.type == "connection_ping",
        Notification.template_key.in_(("connection_ping", "engagement_nudge")),
    )
    row = (
        db.query(Notification.id)
        .filter(
            Notification.user_id == user_id,
            family_filter,
            or_(
                and_(
                    Notification.scheduled_for.isnot(None),
                    Notification.scheduled_for > since,
                ),
                and_(
                    Notification.scheduled_for.is_(None),
                    Notification.created_at > since,
                ),
            ),
        )
        .first()
    )
    return row is not None
