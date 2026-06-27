# app/schemas/user_knowledge.py
"""Schemas for User Knowledge layer: profile baseline + facts."""
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class UserProfileKnowledgeRead(BaseModel):
    """GET /user/knowledge response."""
    user_id: int
    display_name: Optional[str] = None
    language: Optional[str] = None
    baseline_summary: Optional[str] = None
    goals_json: Optional[str] = None
    constraints_json: Optional[str] = None
    preferences_json: Optional[str] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileKnowledgeUpsertRequest(BaseModel):
    """PUT /user/knowledge body (authenticated user only; no user_id)."""

    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = None
    language: Optional[str] = None
    baseline_summary: Optional[str] = None
    goals_json: Optional[str] = None
    constraints_json: Optional[str] = None
    preferences_json: Optional[str] = None


class UserProfileKnowledgeUpsert(BaseModel):
    """Legacy PUT /user/knowledge body (includes user_id)."""
    user_id: int
    display_name: Optional[str] = None
    language: Optional[str] = None
    baseline_summary: Optional[str] = None
    goals_json: Optional[str] = None
    constraints_json: Optional[str] = None
    preferences_json: Optional[str] = None


class UserFactRead(BaseModel):
    """Single fact in GET /user/facts response."""
    id: int
    user_id: int
    key: str
    value_json: Optional[str] = None
    source: str
    confidence: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserFactUpsertRequest(BaseModel):
    """POST /user/facts body (authenticated user only; no user_id)."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value_json: Optional[str] = None
    source: Optional[str] = "manual"  # "chat" | "manual" | "device"
    confidence: Optional[float] = 0.7


class UserFactUpsert(BaseModel):
    """Legacy POST /user/facts body (upsert by user_id + key)."""
    user_id: int
    key: str
    value_json: Optional[str] = None
    source: Optional[str] = "manual"  # "chat" | "manual" | "device"
    confidence: Optional[float] = 0.7
