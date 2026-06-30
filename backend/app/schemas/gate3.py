# Gate 3 schemas — care intelligence + knowledge base
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# --- Knowledge base ---

KB_CATEGORIES = Literal[
    "medical_condition", "medication_education", "lifestyle", "nutrition", "exercise",
    "mental_wellbeing", "culture", "sports", "science", "provider_directory",
    "lab_directory", "local_services", "other",
]

TRUST_LEVELS = Literal["official", "clinical_guideline", "vetted_partner", "editorial", "internal"]
INGESTION_STATUS = Literal["draft", "active", "deprecated"]
DOC_STATUS = Literal["draft", "active", "archived"]

RISK_LEVELS = Literal["low", "medium", "high", "emergency"]
SEVERITY_LEVELS = Literal["mild", "moderate", "severe", "unknown"]


class KnowledgeSourceCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    category: KB_CATEGORIES = "other"
    trust_level: TRUST_LEVELS = "editorial"
    source_url: Optional[str] = Field(None, max_length=512)
    locale: str = Field("fa", max_length=16)
    last_checked_at: Optional[datetime] = None
    freshness_policy_days: int = Field(180, ge=1, le=3650)
    ingestion_status: INGESTION_STATUS = "draft"
    license_notes: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class KnowledgeSourceUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(None, min_length=1, max_length=256)
    category: Optional[KB_CATEGORIES] = None
    trust_level: Optional[TRUST_LEVELS] = None
    source_url: Optional[str] = Field(None, max_length=512)
    locale: Optional[str] = Field(None, max_length=16)
    last_checked_at: Optional[datetime] = None
    freshness_policy_days: Optional[int] = Field(None, ge=1, le=3650)
    ingestion_status: Optional[INGESTION_STATUS] = None
    license_notes: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class KnowledgeDocumentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: int
    title: str = Field(..., min_length=1, max_length=512)
    summary: Optional[str] = None
    category: KB_CATEGORIES = "other"
    locale: str = Field("fa", max_length=16)
    region: Optional[str] = Field(None, max_length=128)
    city: Optional[str] = Field(None, max_length=128)
    specialty: Optional[str] = Field(None, max_length=128)
    tags: Optional[List[str]] = None
    status: DOC_STATUS = "draft"
    published_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None


class KnowledgeDocumentUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    summary: Optional[str] = None
    category: Optional[KB_CATEGORIES] = None
    locale: Optional[str] = Field(None, max_length=16)
    region: Optional[str] = Field(None, max_length=128)
    city: Optional[str] = Field(None, max_length=128)
    specialty: Optional[str] = Field(None, max_length=128)
    tags: Optional[List[str]] = None
    status: Optional[DOC_STATUS] = None
    published_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None


class KnowledgeIngestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: int
    document_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=512)
    category: KB_CATEGORIES = "other"
    locale: str = Field("fa", max_length=16)
    region: Optional[str] = Field(None, max_length=128)
    city: Optional[str] = Field(None, max_length=128)
    specialty: Optional[str] = Field(None, max_length=128)
    content: str = Field(..., min_length=1)
    chunk_size: int = Field(800, ge=200, le=4000)


class KnowledgeSearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=500)
    category: Optional[KB_CATEGORIES] = None
    locale: Optional[str] = Field(None, max_length=16)
    limit: int = Field(5, ge=1, le=20)


# --- Safety / care ---

class SafetyCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(..., min_length=1, max_length=2000)


class CareAnalyzeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(..., min_length=1, max_length=2000)
    language: Optional[str] = Field(None, max_length=8)


class RecommendationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field("general", max_length=64)
    title: Optional[str] = Field(None, max_length=256)
    trigger_message: Optional[str] = Field(None, max_length=2000)


class RecommendationPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[Literal["active", "acknowledged", "dismissed"]] = None


class FollowUpCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    linked_recommendation_id: Optional[int] = None


class FollowUpUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    status: Optional[Literal["open", "done", "cancelled"]] = None
    due_at: Optional[datetime] = None


# --- Health Q&A / symptoms ---

class HealthQuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=2000)
    language: Optional[str] = Field(None, max_length=8)


class SymptomReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symptom_label: str = Field(..., min_length=1, max_length=256)
    symptom_code: Optional[str] = Field(None, max_length=64)
    severity: SEVERITY_LEVELS = "unknown"
    body_area: Optional[str] = Field(None, max_length=64)
    duration: Optional[str] = Field(None, max_length=128)
    notes: Optional[str] = None
    reported_at: Optional[datetime] = None


SYMPTOM_STATUSES = Literal["active", "resolved", "cancelled"]


class SymptomReportPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[SYMPTOM_STATUSES] = None
    notes: Optional[str] = Field(None, max_length=2000)
