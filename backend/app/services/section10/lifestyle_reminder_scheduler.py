"""Lifestyle reminder generation foundation — requires stored plan data."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags

LIFESTYLE_REMINDER_TYPES = frozenset({
    "meal",
    "exercise",
    "hydration",
    "sleep",
    "habit",
    "daily_plan",
    "weekly_plan",
})


def _habit_has_reminder_opt_in(habit: models.UserHabit) -> bool:
    return habit.status == "active" and habit.source in {"manual", "user"}


def process_lifestyle_reminders(db: Session, now: Optional[datetime] = None) -> int:
    if not feature_flags.lifestyle_reminder_scheduler_enabled():
        return 0

    now = now or datetime.utcnow()
    created = 0

    habits = (
        db.query(models.UserHabit)
        .filter(models.UserHabit.status == "active")
        .all()
    )
    for habit in habits:
        if not _habit_has_reminder_opt_in(habit):
            continue
        dedupe = f"lifestyle_habit:{habit.user_id}:{habit.id}:{now.date().isoformat()}"
        existing = (
            db.query(models.Notification)
            .filter(models.Notification.dedupe_key == dedupe)
            .first()
        )
        if existing:
            continue
        notif = models.Notification(
            user_id=habit.user_id,
            type="habit",
            title=habit.name,
            body=f"Habit reminder: {habit.name}",
            template_key="lifestyle_habit_reminder",
            dedupe_key=dedupe,
            status="queued",
            created_at=now,
        )
        db.add(notif)
        created += 1

    lifestyle_events = (
        db.query(models.UserLifestyleEvent)
        .all()
    )
    for ev in lifestyle_events:
        dedupe = f"lifestyle_event:{ev.user_id}:{ev.id}:{now.date().isoformat()}"
        existing = (
            db.query(models.Notification)
            .filter(models.Notification.dedupe_key == dedupe)
            .first()
        )
        if existing:
            continue
        notif = models.Notification(
            user_id=ev.user_id,
            type="lifestyle",
            title=ev.event_type,
            body=f"Lifestyle reminder: {ev.event_type}",
            template_key="lifestyle_event_reminder",
            dedupe_key=dedupe,
            status="queued",
            created_at=now,
        )
        db.add(notif)
        created += 1

    if created:
        db.commit()
    return created
