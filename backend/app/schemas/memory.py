# app/schemas/memory.py
from pydantic import BaseModel
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
    items: List[HistoryGroupItem]


# --- DailyMemorySummary (existing) ---


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

    class Config:
        from_attributes = True  # Pydantic V2: renamed from orm_mode
