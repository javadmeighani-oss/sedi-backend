"""Bounded CareFollowUpTask metadata encoding — no raw transcript."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.services.i10.contextual_followup_types import BOUNDED_META_PREFIX


@dataclass(frozen=True)
class BoundedFollowUpMeta:
    follow_up_kind: str
    user_event_id: Optional[int] = None
    source_notification_id: Optional[int] = None
    notification_id: Optional[int] = None


def pack_description(
    user_description: Optional[str],
    meta: BoundedFollowUpMeta,
) -> str:
    payload = {
        "follow_up_kind": meta.follow_up_kind,
        "user_event_id": meta.user_event_id,
        "source_notification_id": meta.source_notification_id,
        "notification_id": meta.notification_id,
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    prefix = f"{BOUNDED_META_PREFIX}{blob}"
    if user_description:
        return f"{user_description}\n{prefix}"
    return prefix


def parse_bounded_meta(description: Optional[str]) -> tuple[Optional[str], BoundedFollowUpMeta]:
    if not description or BOUNDED_META_PREFIX not in description:
        return description, BoundedFollowUpMeta(follow_up_kind="general_ctx")
    head, _, tail = description.partition(BOUNDED_META_PREFIX)
    user_text = head.strip() or None
    try:
        raw: dict[str, Any] = json.loads(tail)
    except (json.JSONDecodeError, TypeError):
        return user_text, BoundedFollowUpMeta(follow_up_kind="general_ctx")
    return user_text, BoundedFollowUpMeta(
        follow_up_kind=str(raw.get("follow_up_kind") or "general_ctx"),
        user_event_id=raw.get("user_event_id"),
        source_notification_id=raw.get("source_notification_id"),
        notification_id=raw.get("notification_id"),
    )


def with_notification_id(description: Optional[str], notification_id: int) -> str:
    user_text, meta = parse_bounded_meta(description)
    return pack_description(
        user_text,
        BoundedFollowUpMeta(
            follow_up_kind=meta.follow_up_kind,
            user_event_id=meta.user_event_id,
            source_notification_id=meta.source_notification_id,
            notification_id=notification_id,
        ),
    )
