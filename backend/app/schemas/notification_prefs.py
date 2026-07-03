# app/schemas/notification_prefs.py – V1 Notification Preferences API
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, model_validator

HHMM_REGEX = re.compile(r"^\d{2}:\d{2}$")


class NotificationChannelsRead(BaseModel):
    companion: bool = True
    health_alert: bool = True
    reminder_medication: bool = True
    reminder_appointment: bool = True
    reminder_system: bool = True


class NotificationChannelsUpdate(BaseModel):
    companion: Optional[bool] = None
    health_alert: Optional[bool] = None
    reminder_medication: Optional[bool] = None
    reminder_appointment: Optional[bool] = None
    reminder_system: Optional[bool] = None


class QuietHoursRead(BaseModel):
    enabled: bool = False
    start: Optional[str] = None   # HH:MM
    end: Optional[str] = None     # HH:MM


class QuietHoursUpdate(BaseModel):
    enabled: Optional[bool] = None
    start: Optional[str] = None
    end: Optional[str] = None

    @model_validator(mode="after")
    def require_start_end_when_enabled(self):
        if self.enabled is True:
            if not self.start or not self.end:
                raise ValueError("quiet_hours.start and quiet_hours.end are required when enabled is True")
            if not HHMM_REGEX.match(self.start) or not HHMM_REGEX.match(self.end):
                raise ValueError("quiet_hours.start and quiet_hours.end must be HH:MM")
        if self.start is not None and not HHMM_REGEX.match(self.start):
            raise ValueError("quiet_hours.start must be HH:MM")
        if self.end is not None and not HHMM_REGEX.match(self.end):
            raise ValueError("quiet_hours.end must be HH:MM")
        return self


def validate_hhmm_24h(value: str, *, field_name: str = "time") -> str:
    """Validate strict 24-hour HH:MM (00:00–23:59)."""
    text = (value or "").strip()
    if not HHMM_REGEX.match(text):
        raise ValueError(f"{field_name} must be HH:MM")
    hour, minute = map(int, text.split(":"))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"{field_name} must be a valid 24-hour time")
    return text


class NotificationPrefsRead(BaseModel):
    user_id: int
    channels: NotificationChannelsRead = Field(default_factory=NotificationChannelsRead)
    quiet_hours: QuietHoursRead = Field(default_factory=QuietHoursRead)
    engagement_level: int = Field(ge=0, le=2, default=1)
    daily_notification_time: Optional[str] = None


class NotificationPrefsUpdate(BaseModel):
    channels: Optional[NotificationChannelsUpdate] = None
    quiet_hours: Optional[QuietHoursUpdate] = None
    engagement_level: Optional[int] = Field(None, ge=0, le=2)
    daily_notification_time: Optional[str] = None

    @model_validator(mode="after")
    def validate_daily_notification_time(self):
        if self.daily_notification_time is not None:
            validate_hhmm_24h(self.daily_notification_time, field_name="daily_notification_time")
        return self
