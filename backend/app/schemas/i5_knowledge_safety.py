"""I5-IMPL-W2-P02 — dataclasses for conflict / safety / eligibility / freshness views."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class FreshnessInputs:
    now: datetime
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    policy_days: Optional[float] = None


@dataclass(frozen=True)
class ConflictView:
    id: Optional[int]
    conflict_key: str
    knowledge_unit_id_a: int
    knowledge_unit_id_b: int
    conflict_state: str
    conflict_summary: Optional[str] = None
    resolution_note: Optional[str] = None
    idempotency_key: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class SafetyQueueView:
    id: Optional[int]
    queue_item_id: str
    knowledge_unit_id: int
    queue_status: str
    medical_safety_state: str
    high_risk_domain: bool = False
    reason: Optional[str] = None
    decision_id: Optional[int] = None
    idempotency_key: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class EligibilityView:
    knowledge_unit_id: Optional[int]
    runtime_eligibility: str
    provenance_complete: bool = False
    evidence_strength: str = "UNKNOWN"
    freshness_state: str = "UNKNOWN"
    conflict_state: str = "NONE"
    medical_safety_state: str = "UNKNOWN"
    publication_state: str = "DRAFT"
    retraction_reason: Optional[str] = None
