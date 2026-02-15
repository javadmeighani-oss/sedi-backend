# app/schemas/knowledge.py
"""Schemas for Knowledge Capture V1 admin API."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class KcCandidateCreate(BaseModel):
    """POST /knowledge/admin/candidates/create body."""
    user_id: int = Field(..., description="User ID")
    source: str = Field("chat", description="chat | form | import")
    fact_type: str = Field(..., description="e.g. sleep_window, medication, activity_level")
    value_json: str = Field("{}", description="JSON string payload")
    confidence: float = Field(0.7, ge=0, le=1)
    evidence: Optional[str] = Field(None, max_length=500)


class KcCandidateRead(BaseModel):
    """Candidate response."""
    id: int
    user_id: int
    source: str
    fact_type: str
    value_json: str
    confidence: float
    evidence: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class KcUserFactRead(BaseModel):
    """Verified fact response."""
    id: int
    user_id: int
    fact_type: str
    value_json: str
    verified_by: str
    valid_from: datetime
    valid_to: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
