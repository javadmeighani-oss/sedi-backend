# app/schemas/memory.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime

# --- Chat history (Memory table) ---


class HistoryTurnItem(BaseModel):
    """Single conversation turn from memory table."""
    id: int
    created_at: datetime
    user_message: str
    sedi_response: Optional[str] = None
    language: Optional[str] = "en"


class HistoryGroupItem(BaseModel):
    """One group (day/week/month/year) with its turns."""
    key: str  # e.g. "2026-02-11", "2026-W06", "2026-02", "2026"
    turns: List[HistoryTurnItem]


class HistoryResponse(BaseModel):
    """GET /memory/history response."""
    group: str  # "daily" | "weekly" | "monthly" | "yearly"
    timezone: str  # resolved IANA timezone used for grouping
    current_group_key: str  # current bucket key in the user's timezone
    items: List[HistoryGroupItem]


# --- DailyMemorySummary (existing) ---


class MemorySaveRequest(BaseModel):
    """Authenticated daily memory save (no user_id; identity from JWT)."""

    model_config = ConfigDict(extra="forbid")

    summary: Optional[str] = ""
    mood: Optional[str] = None
    context: Optional[str] = None


class MemoryCreate(BaseModel):
    user_id: int
    summary: Optional[str] = None
    mood: Optional[str] = "neutral"
    context: Optional[str] = "chat"


class MemoryResponse(BaseModel):
    id: int
    user_id: int
    summary: Optional[str]
    mood: Optional[str]
    context: Optional[str]
    created_at: datetime
    last_interaction: datetime

    model_config = ConfigDict(from_attributes=True)  # Pydantic V2: renamed from orm_mode


# --- R-021 / M1: user-visible, user-editable memory (I7-owned API over I6 facts + the life timeline) ---


class MemoryFactEditRequest(BaseModel):
    """The user's own correction of one remembered fact. A string is split into a list for list-like facts."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(..., min_length=1, max_length=400)


class LifeEventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field("other", max_length=32)
    summary: Optional[str] = Field(None, max_length=140)
    occurred_at: Optional[datetime] = None
    subject: str = Field("self", max_length=16)
    precision: str = Field("approx", max_length=8)


class LifeEventUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Optional[str] = Field(None, max_length=32)
    summary: Optional[str] = Field(None, max_length=140)
    occurred_at: Optional[datetime] = None
    subject: Optional[str] = Field(None, max_length=16)
    precision: Optional[str] = Field(None, max_length=8)
