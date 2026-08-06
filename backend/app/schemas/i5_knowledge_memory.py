"""I5-IMPL-W2-P01 — Pydantic schemas for knowledge memory / transitions / diffs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class MemoryItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: Optional[int] = None
    memory_item_id: str = Field(..., min_length=1, max_length=64)
    knowledge_unit_id: int = Field(..., gt=0)
    domain: str = Field(..., min_length=1, max_length=128)
    topic: Optional[str] = Field(None, max_length=256)
    knowledge_version: str = Field(..., min_length=1, max_length=64)
    source_ids: Optional[str] = None
    source_versions: Optional[str] = None
    evidence_strength: str = Field("UNKNOWN", max_length=32)
    freshness_state: str = Field("UNKNOWN", max_length=32)
    conflict_state: str = Field("NONE", max_length=32)
    medical_safety_state: str = Field("UNKNOWN", max_length=32)
    runtime_eligibility: str = Field("NOT_ELIGIBLE", max_length=32)
    supersession_state: str = Field("CURRENT", max_length=32)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FieldDiffView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old: Any = None
    new: Any = None


class StructuredDiffView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changed_fields: list[str] = Field(default_factory=list)
    change_kind: str = Field(..., min_length=1, max_length=64)
    field_diffs: dict[str, FieldDiffView] = Field(default_factory=dict)


class TransitionView(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: Optional[int] = None
    memory_row_id: int = Field(..., gt=0)
    memory_item_id: str = Field(..., min_length=1, max_length=64)
    from_knowledge_unit_id: Optional[int] = None
    to_knowledge_unit_id: Optional[int] = None
    transition_kind: str = Field(..., min_length=1, max_length=32)
    change_kind: str = Field(..., min_length=1, max_length=32)
    diff_json: Optional[str] = None
    idempotency_key: str = Field(..., min_length=64, max_length=64)
    reason: Optional[str] = None
    process_id: str = Field("W2P01_SUPERSESSION_SERVICE", max_length=128)
    created_at: Optional[datetime] = None
