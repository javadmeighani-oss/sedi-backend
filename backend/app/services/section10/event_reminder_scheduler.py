"""Event reminder scheduler foundation — default off, canonical I10 intake (B10)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pytz
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags


_BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


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
    from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc

    return event_starts_utc(event)


def recurring_occurrences_utc(event: models.UserEvent, now: datetime) -> List[Tuple[datetime, str]]:
    """DEBT-044: (naive-UTC start, local YYYYMMDD) of each occurrence of a repeating event near ``now``.

    Rules are the two bounded forms Sedi writes from chat: ``FREQ=DAILY`` and ``FREQ=WEEKLY;BYDAY=MO``.
    ``starts_at`` is the first occurrence (its wall-clock time is kept in the event's own timezone, DST-safe).
    Window: yesterday .. +8 days, enough for any offset (max 7 days) and the late-send window.
    """
    rule = (event.recurrence_rule or "").strip().upper()
    first = event.starts_at
    if first is None or not rule.startswith("FREQ="):
        return []
    parts = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        return []
    byday = None
    if freq == "WEEKLY":
        days = [d for d in parts.get("BYDAY", "").split(",") if d in _BYDAY]
        byday = {_BYDAY.index(d) for d in days} or {first.weekday()}
    try:
        tz = pytz.timezone(event.timezone or "Asia/Tehran")
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Asia/Tehran")
    now_local_date = pytz.UTC.localize(now).astimezone(tz).date()
    first_date = first.date()
    out: List[Tuple[datetime, str]] = []
    for delta in range(-1, 9):
        day = now_local_date + timedelta(days=delta)
        if day < first_date or (byday is not None and day.weekday() not in byday):
            continue
        local = tz.localize(datetime.combine(day, first.time()))
        out.append((local.astimezone(pytz.UTC).replace(tzinfo=None), day.strftime("%Y%m%d")))
    return out


# A reminder is sent when its fire time has come; if the scheduler was down it is still sent for this long.
LATE_SEND_WINDOW_MINUTES = 30
# ...but never after the event itself is well underway.
POST_START_LIMIT_MINUTES = 10


def process_event_reminders(db: Session, now: Optional[datetime] = None) -> int:
    if not feature_flags.event_reminder_scheduler_enabled():
        return 0

    from backend.app.services.i10.event_reminder_i10_adapter import (
        build_event_occurrence_key,
        enqueue_event_reminder_notification,
        is_remindable_event,
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
        if not is_remindable_event(event):
            continue
        if event.recurrence_rule:
            occurrences = recurring_occurrences_utc(event, now)
        else:
            single = _event_local_starts_at(event)
            occurrences = [(single, "")] if single is not None else []
        for starts_utc, day_tag in occurrences:
            if now > starts_utc + timedelta(minutes=POST_START_LIMIT_MINUTES):
                continue
            for offset_min in _parse_offsets(event.reminder_offsets_json):
                fire_at = starts_utc - timedelta(minutes=offset_min)
                if fire_at > now or (now - fire_at) > timedelta(minutes=LATE_SEND_WINDOW_MINUTES):
                    continue
                occurrence_key = build_event_occurrence_key(
                    user_id=event.user_id,
                    event_id=event.id,
                    offset_min=offset_min,
                    occurrence_day=day_tag or None,
                )
                result = enqueue_event_reminder_notification(
                    db,
                    event=event,
                    user_id=event.user_id,
                    occurrence_key=occurrence_key,
                    offset_min=offset_min,
                    starts_utc_override=starts_utc if day_tag else None,
                )
                if result is not None:
                    created += 1
    return created
