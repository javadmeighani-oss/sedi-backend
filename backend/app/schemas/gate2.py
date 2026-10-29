# app/schemas/gate2.py — Gate 2 unified user data layer
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_RECURRENCE_DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def normalize_recurrence_rule(value: Optional[str]) -> Optional[str]:
    """The only repeat shapes Sedi's reminder scheduler understands (chat and the My Schedule sheet write these):

    ``FREQ=DAILY`` | ``FREQ=WEEKLY`` | ``FREQ=WEEKLY;BYDAY=MO,WE,SA`` (the SAME time on those weekdays).
    Empty means "no repeat". Anything else is rejected instead of being stored and silently never firing.
    """
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in ("FREQ=DAILY", "FREQ=WEEKLY"):
        return text
    if text.startswith("FREQ=WEEKLY;BYDAY="):
        codes = [c.strip() for c in text[len("FREQ=WEEKLY;BYDAY="):].split(",")]
        if codes and all(c in _RECURRENCE_DAYS for c in codes) and len(set(codes)) == len(codes):
            ordered = sorted(codes, key=_RECURRENCE_DAYS.index)
            return "FREQ=WEEKLY;BYDAY=" + ",".join(ordered)
    raise ValueError("recurrence_rule must be FREQ=DAILY, FREQ=WEEKLY or FREQ=WEEKLY;BYDAY=MO,WE,...")

GATE2_SOURCES = frozenset({"manual", "conversation", "system", "caregiver"})
HABIT_STATUSES = frozenset({"active", "paused", "completed", "inactive"})
GOAL_CATEGORIES = frozenset({"health", "fitness", "lifestyle", "motivation", "other"})
GOAL_STATUSES = frozenset({"active", "completed", "cancelled", "paused"})
RESTRICTION_TYPES = frozenset({"diet", "exercise", "other"})
RESTRICTION_STATUSES = frozenset({"active", "inactive"})
EVENT_DOMAINS = frozenset({"personal", "work", "education", "medical", "care", "family", "lifestyle", "other"})
EVENT_TYPES = frozenset({
    "birthday", "important_day", "work_meeting", "exam", "deadline",
    "doctor_visit", "lab_test", "imaging", "surgery", "physiotherapy",
    "nursing_visit", "care_followup", "medication_review", "other",
})
EVENT_STATUSES = frozenset({"scheduled", "completed", "cancelled", "postponed"})
EVENT_IMPORTANCE = frozenset({"low", "normal", "high", "critical"})
CARE_PLAN_STATUSES = frozenset({"active", "completed", "cancelled", "paused"})


def _require_in(value: str, allowed: frozenset, field_name: str) -> str:
    v = (value or "").strip()
    if v not in allowed:
        raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed))}")
    return v


class HabitCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=128)
    frequency: Optional[str] = Field(None, max_length=64)
    target: Optional[Any] = None
    status: Literal["active", "paused", "completed", "inactive"] = "active"
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"
    notes: Optional[str] = None


class HabitUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    frequency: Optional[str] = Field(None, max_length=64)
    target: Optional[Any] = None
    status: Optional[Literal["active", "paused", "completed", "inactive"]] = None
    notes: Optional[str] = None


class GoalCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["health", "fitness", "lifestyle", "motivation", "other"] = "lifestyle"
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    target: Optional[Any] = None
    status: Literal["active", "completed", "cancelled", "paused"] = "active"
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"
    priority: Optional[Literal["low", "normal", "high"]] = None


class GoalUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Optional[Literal["health", "fitness", "lifestyle", "motivation", "other"]] = None
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    target: Optional[Any] = None
    status: Optional[Literal["active", "completed", "cancelled", "paused"]] = None
    priority: Optional[Literal["low", "normal", "high"]] = None


class RestrictionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    restriction_type: Literal["diet", "exercise", "other"]
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    severity: Optional[Literal["low", "medium", "high"]] = None
    status: Literal["active", "inactive"] = "active"
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"


class RestrictionUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    restriction_type: Optional[Literal["diet", "exercise", "other"]] = None
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    severity: Optional[Literal["low", "medium", "high"]] = None
    status: Optional[Literal["active", "inactive"]] = None


class DoctorCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=128)
    specialty: Optional[str] = Field(None, max_length=128)
    phone: Optional[str] = Field(None, max_length=32)
    clinic: Optional[str] = Field(None, max_length=256)
    notes: Optional[str] = None
    is_primary: bool = False
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"


class DoctorUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    specialty: Optional[str] = Field(None, max_length=128)
    phone: Optional[str] = Field(None, max_length=32)
    clinic: Optional[str] = Field(None, max_length=256)
    notes: Optional[str] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None


class EventCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    event_domain: Literal["personal", "work", "education", "medical", "care", "family", "lifestyle", "other"] = "other"
    event_type: Literal[
        "birthday", "important_day", "work_meeting", "exam", "deadline",
        "doctor_visit", "lab_test", "imaging", "surgery", "physiotherapy",
        "nursing_visit", "care_followup", "medication_review", "other",
    ] = "other"
    starts_at: datetime
    ends_at: Optional[datetime] = None
    timezone: Optional[str] = Field(None, max_length=64)
    location: Optional[str] = Field(None, max_length=256)
    doctor_id: Optional[int] = None
    status: Literal["scheduled", "completed", "cancelled", "postponed"] = "scheduled"
    importance: Literal["low", "normal", "high", "critical"] = "normal"
    reminder_enabled: bool = False
    reminder_offsets: Optional[List[int]] = None
    recurrence_rule: Optional[str] = None
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"
    notes: Optional[str] = None

    @field_validator("recurrence_rule")
    @classmethod
    def _bounded_recurrence(cls, v: Optional[str]) -> Optional[str]:
        return normalize_recurrence_rule(v)


class EventUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    event_domain: Optional[Literal["personal", "work", "education", "medical", "care", "family", "lifestyle", "other"]] = None
    event_type: Optional[Literal[
        "birthday", "important_day", "work_meeting", "exam", "deadline",
        "doctor_visit", "lab_test", "imaging", "surgery", "physiotherapy",
        "nursing_visit", "care_followup", "medication_review", "other",
    ]] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    timezone: Optional[str] = Field(None, max_length=64)
    location: Optional[str] = Field(None, max_length=256)
    doctor_id: Optional[int] = None
    status: Optional[Literal["scheduled", "completed", "cancelled", "postponed"]] = None
    importance: Optional[Literal["low", "normal", "high", "critical"]] = None
    reminder_enabled: Optional[bool] = None
    reminder_offsets: Optional[List[int]] = None
    recurrence_rule: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("recurrence_rule")
    @classmethod
    def _bounded_recurrence(cls, v: Optional[str]) -> Optional[str]:
        return normalize_recurrence_rule(v)


class LifestyleEventCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = Field(..., min_length=1, max_length=64)
    value: Optional[Any] = None
    occurred_at: datetime
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"
    notes: Optional[str] = None


class CarePlanItemCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    status: Literal["active", "completed", "cancelled", "paused"] = "active"
    scheduled_at: Optional[datetime] = None
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"
    notes: Optional[str] = None


class CarePlanItemUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    status: Optional[Literal["active", "completed", "cancelled", "paused"]] = None
    scheduled_at: Optional[datetime] = None
    notes: Optional[str] = None
