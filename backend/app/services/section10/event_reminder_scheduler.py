"""Event reminder scheduler foundation — default off, canonical I10 intake (B10)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional

import pytz
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags


def _parse_offsets(reminder_offsets_json: Optional[str]) -> List[int]:
    if not reminder_offsets_json:
        return [60]
    try:
        data = json.loads(reminder_offsets_json)
        if isinstance(data, list):
            return [int(x) for x in data if isinstance(x, (int, float))]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return [60]


def _event_local_starts_at(event: models.UserEvent) -> Optional[datetime]:
    tz_name = event.timezone or "Asia/Tehran"
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Asia/Tehran")
    starts = event.starts_at
    if starts.tzinfo is None:
        starts = tz.localize(starts)
    return starts.astimezone(pytz.UTC).replace(tzinfo=None)


def process_event_reminders(db: Session, now: Optional[datetime] = None) -> int:
    if not feature_flags.event_reminder_scheduler_enabled():
        return 0

    from backend.app.services.i10.event_reminder_i10_adapter import (
        build_event_occurrence_key,
        enqueue_event_reminder_notification,
        is_medical_remindable_event,
    )

    now = now or datetime.utcnow()
    created = 0
    rows = (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.reminder_enabled == True,  # noqa: E712
            models.UserEvent.status.in_(["scheduled", "confirmed"]),
        )
        .all()
    )
    for event in rows:
        if not is_medical_remindable_event(event):
            continue
        starts_utc = _event_local_starts_at(event)
        if starts_utc is None or starts_utc <= now:
            continue
        for offset_min in _parse_offsets(event.reminder_offsets_json):
            fire_at = starts_utc - timedelta(minutes=offset_min)
            if fire_at > now or (now - fire_at) > timedelta(minutes=30):
                continue
            occurrence_key = build_event_occurrence_key(
                user_id=event.user_id, event_id=event.id, offset_min=offset_min
            )
            result = enqueue_event_reminder_notification(
                db,
                event=event,
                user_id=event.user_id,
                occurrence_key=occurrence_key,
                offset_min=offset_min,
            )
            if result is not None:
                created += 1
    return created
