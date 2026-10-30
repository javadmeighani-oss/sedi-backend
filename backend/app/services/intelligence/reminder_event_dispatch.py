"""I1 dispatch: persist I3-ready reminder/event drafts via existing UserEvent service.

No direct Notification insert. I10 consumes UserEvent reminder fields via scheduler.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate2 import EventCreateIn
from backend.app.services.gate2_data_service import create_event
from backend.app.services.intelligence.reminder_event_readiness import (
    ReminderEventDraft,
    describe_when,
    parse_reminder_event_draft,
)
from backend.app import sedi_copy


def find_duplicate_conversation_event(
    db: Session,
    *,
    user_id: int,
    title: str,
    starts_at: datetime,
    event_type: str,
) -> Optional[models.UserEvent]:
    return (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.user_id == int(user_id),
            models.UserEvent.source == "conversation",
            models.UserEvent.title == title,
            models.UserEvent.event_type == event_type,
            models.UserEvent.starts_at == starts_at,
            models.UserEvent.status.in_(("scheduled", "confirmed")),
        )
        .first()
    )


def dispatch_reminder_user_event(
    db: Session,
    *,
    user_id: int,
    message: str,
    timezone_name: Optional[str],
    now_utc: Optional[datetime] = None,
    draft: Optional[ReminderEventDraft] = None,
    language: Optional[str] = None,
) -> dict[str, Any]:
    """Create at most one UserEvent for a READY reminder/event draft."""
    resolved = draft
    if resolved is None:
        resolved, missing = parse_reminder_event_draft(
            message=message, timezone_name=timezone_name, now_utc=now_utc, language=language
        )
        if missing is not None or resolved is None:
            return {"created": False, "reason": "not_ready"}

    dup = find_duplicate_conversation_event(
        db,
        user_id=user_id,
        title=resolved.title,
        starts_at=resolved.starts_at_local,
        event_type=resolved.event_type,
    )
    lang = language if language in ("fa", "ar", "en") else "en"
    offsets_for_reply = list(resolved.reminder_offsets) if resolved.reminder_offsets else []
    info = {
        "when": describe_when(resolved, lang, now_utc),
        "title": resolved.title,
        "offset_min": offsets_for_reply[0] if offsets_for_reply else None,
    }
    if dup is not None:
        return {
            "created": False,
            "duplicate": True,
            "user_event_id": dup.id,
            "reason": "duplicate",
            **info,
        }

    offsets = list(resolved.reminder_offsets) if resolved.reminder_offsets else None
    body = EventCreateIn(
        title=resolved.title,
        event_domain=resolved.event_domain,  # type: ignore[arg-type]
        event_type=resolved.event_type,  # type: ignore[arg-type]
        starts_at=resolved.starts_at_local,
        timezone=resolved.timezone_name,
        status="scheduled",
        importance=resolved.importance,  # type: ignore[arg-type]
        reminder_enabled=bool(resolved.reminder_enabled),
        reminder_offsets=offsets,
        recurrence_rule=resolved.recurrence_rule,
        source="conversation",
    )
    event = create_event(db, user_id, body)
    return {
        "created": True,
        "duplicate": False,
        "user_event_id": event.get("id"),
        "reason": "created",
        **info,
    }


def _lead_text(offset_min: int, lang: str) -> str:
    if offset_min % 1440 == 0:
        if offset_min == 1440:
            return sedi_copy.t("reminder.lead_text.day_one", lang)
        return sedi_copy.t("reminder.lead_text.days", lang, n=offset_min // 1440)
    if offset_min % 60 == 0:
        if offset_min == 60:
            return sedi_copy.t("reminder.lead_text.hour_one", lang)
        return sedi_copy.t("reminder.lead_text.hours", lang, n=offset_min // 60)
    return sedi_copy.t("reminder.lead_text.minutes", lang, n=offset_min)


def confirmation_message(dispatched: dict[str, Any], lang: str) -> str:
    """Warm confirmation that states WHAT and WHEN (R-011/R-026) - never a vague "I'll remind you"."""
    when = dispatched.get("when") or ""
    title = dispatched.get("title") or ""
    offset = dispatched.get("offset_min")
    lang3 = lang if lang in ("fa", "ar") else "en"
    if offset:
        return sedi_copy.t("reminder.confirm.with_lead", lang3, title=title, when=when, lead=_lead_text(int(offset), lang3))
    return sedi_copy.t("reminder.confirm.at_time", lang3, title=title, when=when)
