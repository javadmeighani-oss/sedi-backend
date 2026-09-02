"""I10-B17 — domain-safe notification interaction recorder (ledger-only by default)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models import InteractionEvent, Notification, NotificationFeedback
from backend.app.services.gate4.interaction_event_service import create_interaction_event
from backend.app.services.i10.interaction_vocabulary import (
    VOCABULARY_VERSION,
    CanonicalInteractionVerb,
    assert_generic_verb_cannot_complete_domain,
    event_type_for_verb,
    resolve_interaction_verb,
)

_log = logging.getLogger(__name__)


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
) -> InteractionRecordResult:
    """
    Persist NotificationFeedback + InteractionEvent without domain mutation.

    Domain completion (medication taken, I8 action completed, etc.) remains on
    authorized source-domain endpoints only.
    """
    resolved = resolve_interaction_verb(payload)
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
