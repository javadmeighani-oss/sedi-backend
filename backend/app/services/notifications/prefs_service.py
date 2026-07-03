# backend/app/services/notifications/prefs_service.py – V1 Notification Preferences
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.app.models import NotificationPrefs, User
from backend.app.schemas.notification_prefs import (
    NotificationChannelsRead,
    NotificationChannelsUpdate,
    NotificationPrefsRead,
    NotificationPrefsUpdate,
    QuietHoursRead,
    QuietHoursUpdate,
)


def _defaults_read(user_id: int) -> NotificationPrefsRead:
    return NotificationPrefsRead(
        user_id=user_id,
        channels=NotificationChannelsRead(
            companion=True,
            health_alert=True,
            reminder_medication=True,
            reminder_appointment=True,
            reminder_system=True,
        ),
        quiet_hours=QuietHoursRead(enabled=False, start=None, end=None),
        engagement_level=1,
        daily_notification_time=None,
    )


def _row_to_read(row: NotificationPrefs) -> NotificationPrefsRead:
    return NotificationPrefsRead(
        user_id=row.user_id,
        channels=NotificationChannelsRead(
            companion=row.companion_enabled,
            health_alert=row.health_alert_enabled,
            reminder_medication=row.reminder_medication_enabled,
            reminder_appointment=row.reminder_appointment_enabled,
            reminder_system=row.reminder_system_enabled,
        ),
        quiet_hours=QuietHoursRead(
            enabled=row.quiet_hours_enabled,
            start=row.quiet_start,
            end=row.quiet_end,
        ),
        engagement_level=row.engagement_level,
        daily_notification_time=row.daily_notification_time,
    )


def get_prefs(db: Session, user_id: int) -> NotificationPrefsRead:
    """Return stored prefs or defaults (fail-open: no row => defaults)."""
    row = db.query(NotificationPrefs).filter(NotificationPrefs.user_id == user_id).first()
    if row is None:
        return _defaults_read(user_id)
    return _row_to_read(row)


def upsert_prefs(db: Session, user_id: int, payload: NotificationPrefsUpdate) -> NotificationPrefsRead:
    """Create or update one row; return current prefs. Partial update: omit field => keep existing or default."""
    row = db.query(NotificationPrefs).filter(NotificationPrefs.user_id == user_id).first()
    if row is None:
        row = NotificationPrefs(user_id=user_id)
        db.add(row)
        db.flush()

    update = payload.model_dump(exclude_unset=True)
    if not update:
        return _row_to_read(row)

    if "channels" in update and update["channels"] is not None:
        ch: Dict[str, Any] = update["channels"]
        if "companion" in ch and ch["companion"] is not None:
            row.companion_enabled = ch["companion"]
        if "health_alert" in ch and ch["health_alert"] is not None:
            row.health_alert_enabled = ch["health_alert"]
        if "reminder_medication" in ch and ch["reminder_medication"] is not None:
            row.reminder_medication_enabled = ch["reminder_medication"]
        if "reminder_appointment" in ch and ch["reminder_appointment"] is not None:
            row.reminder_appointment_enabled = ch["reminder_appointment"]
        if "reminder_system" in ch and ch["reminder_system"] is not None:
            row.reminder_system_enabled = ch["reminder_system"]

    if "quiet_hours" in update and update["quiet_hours"] is not None:
        qh: Dict[str, Any] = update["quiet_hours"]
        if "enabled" in qh and qh["enabled"] is not None:
            row.quiet_hours_enabled = qh["enabled"]
        if "start" in qh:
            row.quiet_start = qh["start"]
        if "end" in qh:
            row.quiet_end = qh["end"]

    if "engagement_level" in update and update["engagement_level"] is not None:
        row.engagement_level = update["engagement_level"]

    if "daily_notification_time" in update:
        row.daily_notification_time = update["daily_notification_time"]

    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_read(row)
