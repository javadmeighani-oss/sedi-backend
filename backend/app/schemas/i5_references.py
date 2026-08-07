"""I5-IMPL-W4-P02 — schemas for grounded synthesis + reference / disclosure envelopes."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReferenceItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_unit_id: int = Field(..., gt=0)
    canonical_unit_id: str = Field(..., min_length=1, max_length=128)
    immutable_version_id: str = Field(..., min_length=1, max_length=128)
    memory_item_id: Optional[str] = Field(None, max_length=64)
    provenance_id: Optional[int] = None
    source_profile_id: Optional[int] = None
    raw_evidence_id: Optional[int] = None
    label: str = Field(..., min_length=1, max_length=256)
    evidence_strength: str = Field(..., max_length=32)
    statement_excerpt: str = Field(..., min_length=1)


class SupportedClaimView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(..., min_length=1, max_length=64)
    claim_text: str = Field(..., min_length=1)
    claim_kind: str = Field(..., min_length=1, max_length=64)
    evidence_knowledge_unit_ids: list[int] = Field(default_factory=list)
    evidence_labels: list[str] = Field(default_factory=list)


class DisclosureView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1)
    mandatory: bool = True


class PersonalizationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Optional[str] = Field(None, max_length=16)
    tone: str = Field("neutral_educational", max_length=64)
    format_hint: str = Field("show_sources_block", max_length=64)
    medical_facts_altered: bool = False


class GroundedAnswerView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_id: str = Field(..., min_length=1, max_length=64)
    management_alias: str = Field(..., min_length=1, max_length=16)
    status: str = Field(..., min_length=1, max_length=64)
    query_id: Optional[str] = None
    trace_id: Optional[str] = None
    synthesized_text: str = ""
    claims: list[SupportedClaimView] = Field(default_factory=list)
    unsupported_claims_rejected: list[str] = Field(default_factory=list)
    references: list[ReferenceItemView] = Field(default_factory=list)
    show_sources: list[str] = Field(default_factory=list)
    why_sedi_said_this: list[str] = Field(default_factory=list)
    disclosures: list[DisclosureView] = Field(default_factory=list)
    personalization: PersonalizationView = Field(default_factory=PersonalizationView)
    no_base_model_fallback: bool = True
    chat_metadata: dict[str, Any] = Field(default_factory=dict)
