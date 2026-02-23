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


class NotificationPrefsRead(BaseModel):
    user_id: int
    channels: NotificationChannelsRead = Field(default_factory=NotificationChannelsRead)
    quiet_hours: QuietHoursRead = Field(default_factory=QuietHoursRead)
    engagement_level: int = Field(ge=0, le=2, default=1)


class NotificationPrefsUpdate(BaseModel):
    channels: Optional[NotificationChannelsUpdate] = None
    quiet_hours: Optional[QuietHoursUpdate] = None
    engagement_level: Optional[int] = Field(None, ge=0, le=2)
