# backend.app.services.user_context.context_models
"""
Pydantic models for UserContextPack (Stage 23 Step 1).
Read-only context pack: identity + preferences + lifestyle + memory summary.
V1: permissive types; optional fields where data may be missing.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QuietHours(BaseModel):
    """User quiet hours window (e.g. do-not-disturb)."""
    start: Optional[str] = None  # e.g. "22:00"
    end: Optional[str] = None    # e.g. "08:00"


class UserGoals(BaseModel):
    """Optional user goals list."""
    items: List[str] = Field(default_factory=list)


class UserLifestyleSummary(BaseModel):
    """Minimal lifestyle summary text + optional extracted facts."""
    text: Optional[str] = None
    extracted_facts: Dict[str, Any] = Field(default_factory=dict)


class UserContextPack(BaseModel):
    """Aggregated read-only context pack for a user."""
    user_id: int
    preferred_name: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    quiet_hours: QuietHours = Field(default_factory=QuietHours)
    engagement_level: Optional[str] = None  # low | normal | high if known
    goals: Optional[UserGoals] = None
    lifestyle: UserLifestyleSummary = Field(default_factory=UserLifestyleSummary)
    daily_memory_summary: Optional[str] = None
    verified_facts: Dict[str, Any] = Field(default_factory=dict)  # stable facts (only if verified available)
    source_meta: Dict[str, Any] = Field(default_factory=dict)  # e.g. facts_source, etc.
    birth_year: Optional[int] = None
    sex: Optional[str] = None
    addressing_preference: Optional[str] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[float] = None
