"""I5-IMPL-W1-P02 — Pydantic schemas for KU / provenance / raw evidence."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeUnitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_unit_id: str = Field(..., min_length=1, max_length=64)
    immutable_version_id: str = Field(..., min_length=1, max_length=64)
    domain: str = Field(..., min_length=1, max_length=128)
    topic_taxonomy: Optional[str] = Field(None, max_length=256)
    disease_or_health_condition: Optional[str] = Field(None, max_length=256)
    manifest_entity_id: Optional[str] = Field(None, max_length=16)
    manifest_track_id: Optional[str] = Field(None, max_length=64)
    language: str = Field("en", min_length=1, max_length=32)
    knowledge_type: str = Field(..., min_length=1, max_length=32)
    normalized_statement: str = Field(..., min_length=1)
    applicability: Optional[str] = None
    exclusions: Optional[str] = None
    population: Optional[str] = Field(None, max_length=256)
    jurisdiction: Optional[str] = Field(None, max_length=64)
    evidence_strength: str = Field("UNKNOWN", max_length=32)
    medical_safety_state: str = Field("UNKNOWN", max_length=32)
    conflict_state: str = Field("NONE", max_length=32)
    freshness_state: str = Field("UNKNOWN", max_length=32)
    review_state: str = Field("NOT_REVIEWED", max_length=32)
    publication_state: str = Field("DRAFT", max_length=32)
    runtime_eligibility: str = Field("NOT_ELIGIBLE", max_length=32)
    provenance_complete: bool = False
    deduplication_key: str = Field(..., min_length=64, max_length=64)
    canonical_hash: str = Field(..., min_length=64, max_length=64)
    hash_algorithm: str = Field("SHA-256", max_length=32)
    canonicalization_version: str = Field("v1", max_length=32)
    supersedes_unit_id: Optional[int] = None
    retraction_reason: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class KnowledgeUnitRead(KnowledgeUnitCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    created_at: datetime
    updated_at: datetime
    last_reviewed_at: Optional[datetime] = None


class KnowledgeProvenanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_unit_id: int = Field(..., gt=0)
    source_profile_id: int = Field(..., gt=0)
    source_document_id: Optional[str] = Field(None, max_length=128)
    source_version_id: Optional[str] = Field(None, max_length=128)
    raw_evidence_id: Optional[int] = None
    retrieval_method: str = Field(..., min_length=1, max_length=128)
    access_route: Optional[str] = Field(None, max_length=128)
    content_hash: Optional[str] = Field(None, min_length=64, max_length=64)
    byte_hash: Optional[str] = Field(None, min_length=64, max_length=64)
    normalized_hash: Optional[str] = Field(None, min_length=64, max_length=64)
    extraction_process: Optional[str] = Field(None, max_length=256)
    normalization_process: Optional[str] = Field(None, max_length=256)
    review_decision_id: Optional[int] = None
    attribution_data: Optional[str] = None
    citation_rendering_data: Optional[str] = None
    conflict_hook: Optional[str] = Field(None, max_length=256)
    supersession_hook: Optional[str] = Field(None, max_length=256)
    retraction_hook: Optional[str] = Field(None, max_length=256)


class KnowledgeProvenanceRead(KnowledgeProvenanceCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    created_at: datetime


class I5RawEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_profile_id: int = Field(..., gt=0)
    source_document_id: Optional[str] = Field(None, max_length=128)
    source_version_id: Optional[str] = Field(None, max_length=128)
    retrieval_run_id: Optional[int] = None
    retrieval_timestamp: datetime
    canonical_url: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=64, max_length=64)
    byte_hash: Optional[str] = Field(None, min_length=64, max_length=64)
    normalized_hash: Optional[str] = Field(None, min_length=64, max_length=64)
    hash_algorithm: str = Field("SHA-256", max_length=32)
    mime_type: Optional[str] = Field(None, max_length=128)
    language: Optional[str] = Field(None, max_length=32)
    jurisdiction: Optional[str] = Field(None, max_length=64)
    storage_mode: str = Field("NONE", max_length=64)
    retention_mode: str = Field(..., min_length=1, max_length=64)
    rights_terms_state: str = Field("UNKNOWN", max_length=32)
    robots_access_state: str = Field("UNKNOWN", max_length=32)
    redaction_state: str = Field("NONE", max_length=32)
    prohibited_data_state: str = Field("UNKNOWN", max_length=32)
    expiry_state: str = Field("ACTIVE", max_length=32)
    supersedes_raw_evidence_id: Optional[int] = None
    created_by_run_id: Optional[int] = None


class I5RawEvidenceRead(I5RawEvidenceCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    created_at: datetime
