"""I10 delivery readiness — NotificationPrefs + PushDevice (not authorization)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.policy_types import I10NotificationScope


def has_active_push_device(db: Session, user_id: int) -> bool:
    row = (
        db.query(models.PushDevice)
        .filter(
            models.PushDevice.user_id == user_id,
            models.PushDevice.is_active.is_(True),
            models.PushDevice.fcm_token.isnot(None),
        )
        .first()
    )
    return row is not None


def notification_prefs_allow_scope(
    db: Session,
    user_id: int,
    notification_scope: I10NotificationScope,
) -> tuple[bool, str]:
    """Map I10 scope to existing NotificationPrefs toggles (conservative)."""
    prefs = db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == user_id).first()
    if prefs is None:
        return True, "PREFS_DEFAULT_ALLOW"
    if notification_scope in (
        I10NotificationScope.SAFETY_ESCALATION,
        I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
        I10NotificationScope.GENERAL_STATUS,
        I10NotificationScope.DEVICE_STATUS,
    ):
        if not prefs.health_alert_enabled:
            return False, "NOTIFICATION_PREFS_HEALTH_ALERT_DISABLED"
    if notification_scope == I10NotificationScope.CARE_ACTION:
        if not prefs.reminder_system_enabled:
            return False, "NOTIFICATION_PREFS_REMINDER_DISABLED"
    if not prefs.companion_enabled and notification_scope == I10NotificationScope.GENERAL_STATUS:
        return False, "NOTIFICATION_PREFS_COMPANION_DISABLED"
    return True, "PREFS_ALLOWED"
