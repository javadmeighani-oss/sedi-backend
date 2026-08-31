"""Medication reminder scheduling (Phase V1.1B)."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from typing import Optional

import pytz
from sqlalchemy.orm import Session, joinedload

from backend.app import models
from backend.app.services.notifications.prefs_service import get_prefs
from backend.app.services.user_medication_service import DEFAULT_TIMEZONE, format_time_of_day

SCHEDULE_WINDOW_MINUTES = 15


def _medication_reminders_enabled(db: Session, user_id: int) -> bool:
    try:
        return get_prefs(db, user_id).channels.reminder_medication
    except Exception:
        return True


def _day_matches(local_now: datetime, days_of_week: Optional[str]) -> bool:
    if not days_of_week or not str(days_of_week).strip():
        return True
    allowed = {int(x.strip()) for x in str(days_of_week).split(",") if x.strip().isdigit()}
    if not allowed:
        return True
    return local_now.weekday() in allowed


def _is_schedule_due(local_now: datetime, time_of_day: time, window_minutes: int = SCHEDULE_WINDOW_MINUTES) -> bool:
    scheduled = local_now.replace(
        hour=time_of_day.hour,
        minute=time_of_day.minute,
        second=0,
        microsecond=0,
    )
    delta_min = (local_now - scheduled).total_seconds() / 60.0
    return 0 <= delta_min < window_minutes


def process_medication_reminders(db: Session, decision_engine, now_utc: Optional[datetime] = None) -> int:
    """
    Create medication reminder notifications for due schedule times.
    Returns count of notifications created.
    Legacy rows without schedules use 8-hour bucket dedupe (unchanged).
    """
    created = 0
    if now_utc is None:
        now_utc = datetime.utcnow()

    rows = (
        db.query(models.UserMedication, models.Medication)
        .join(models.Medication, models.UserMedication.medication_id == models.Medication.id)
        .options(joinedload(models.UserMedication.schedules))
        .filter(models.UserMedication.reminder_enabled.is_(True))
        .all()
    )

    for um, med in rows:
        if not _medication_reminders_enabled(db, um.user_id):
            continue

        dosage = um.user_dosage or med.default_dosage
        tz_name = um.timezone or DEFAULT_TIMEZONE
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.timezone(DEFAULT_TIMEZONE)
        local_now = now_utc.replace(tzinfo=pytz.UTC).astimezone(tz)

        schedules = um.schedules or []
        if schedules:
            for sch in schedules:
                if not _day_matches(local_now, sch.days_of_week):
                    continue
                if not _is_schedule_due(local_now, sch.time_of_day):
                    continue
                slot = format_time_of_day(sch.time_of_day)
                scheduled_local = local_now.replace(
                    hour=sch.time_of_day.hour,
                    minute=sch.time_of_day.minute,
                    second=0,
                    microsecond=0,
                )
                scheduled_for_utc = scheduled_local.astimezone(pytz.UTC).replace(tzinfo=None)
                result = decision_engine.create_medication_reminder(
                    user_id=um.user_id,
                    medication_name=med.name,
                    dosage=dosage,
                    medication_id=med.id,
                    schedule_time=slot,
                    user_medication_id=um.id,
                    schedule_id=sch.id,
                    scheduled_for_utc=scheduled_for_utc,
                )
                if result:
                    created += 1
        else:
            result = decision_engine.create_medication_reminder(
                user_id=um.user_id,
                medication_name=med.name,
                dosage=dosage,
                medication_id=med.id,
                scheduled_for_utc=now_utc,
                user_medication_id=um.id,
            )
            if result:
                created += 1

    return created
