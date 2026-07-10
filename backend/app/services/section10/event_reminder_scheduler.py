"""Event reminder scheduler foundation — default off, Gate 4 notification creation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional

import pytz
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags

MEDICAL_EVENT_TYPES = frozenset({
    "doctor_visit",
    "lab_test",
    "medical_follow_up",
    "imaging",
    "surgery",
    "care_followup",
})


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
        if event.event_type not in MEDICAL_EVENT_TYPES and event.event_domain not in {"medical", "care"}:
            continue
        starts_utc = _event_local_starts_at(event)
        if starts_utc is None or starts_utc <= now:
            continue
        for offset_min in _parse_offsets(event.reminder_offsets_json):
            fire_at = starts_utc - timedelta(minutes=offset_min)
            if fire_at > now or (now - fire_at) > timedelta(minutes=30):
                continue
            dedupe = f"event_reminder:{event.user_id}:{event.id}:{offset_min}"
            existing = (
                db.query(models.Notification)
                .filter(models.Notification.dedupe_key == dedupe)
                .first()
            )
            if existing:
                continue
            notif = models.Notification(
                user_id=event.user_id,
                type="event_reminder",
                title=event.title,
                body=f"Reminder: {event.title}",
                template_key="event_reminder",
                dedupe_key=dedupe,
                status="queued",
                created_at=now,
            )
            db.add(notif)
            created += 1
    if created:
        db.commit()
    return created
