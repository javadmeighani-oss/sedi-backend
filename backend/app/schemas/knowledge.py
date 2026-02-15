# app/schemas/knowledge.py
"""Schemas for Knowledge Capture V1 API."""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class NextQuestionData(BaseModel):
    """GET /knowledge/next_question data payload."""
    user_id: int
    question_id: str
    field_key: str
    text: str
    options: List[str] = []
    reason: str = ""
    question_type: Optional[str] = None  # confirm_candidate when confirmation needed
    candidate_id: Optional[int] = None  # for confirm_candidate


class ExtractFromMessageRequest(BaseModel):
    """POST /knowledge/extract_from_message body."""
    user_id: int = Field(..., description="User ID")
    text: str = Field(..., description="Chat message text to extract from")
    language: str = Field("fa", description="Language code: fa, en, ...")
    source_message_id: Optional[str] = Field(None, description="Optional message ID for tracing")


class ApplyAnswerRequest(BaseModel):
    """POST /knowledge/admin/answers/apply or /knowledge/apply_answer body."""
    user_id: int = Field(..., description="User ID")
    field_key: Optional[str] = Field(None, description="birth_year, sex, ... or fact_type")
    value: Optional[Any] = Field(None, description="Scalar or JSON-serializable value")
    answer: Optional[str] = Field(None, description="For confirm_candidate: raw answer (alias for value)")
    candidate_id: Optional[int] = Field(None, description="For confirm_candidate: candidate to accept/reject")
    question_type: Optional[str] = Field(None, description="confirm_candidate when answering Yes/No")


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
