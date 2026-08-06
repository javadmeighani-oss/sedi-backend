"""I5-IMPL-W2-P03 — admin review surface schemas (KU / gap / safety / conflict).

Authority: package_sequence OBJECTIVE=Admin review surfaces; MODELS=[].
No new ORM. DTOs only for admin list/filter/claim/close/resolve operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


PACKAGE_ID = "I5-IMPL-W2-P03"
MANAGEMENT_ALIAS = "P05"
PACKAGE_TITLE = "Admin review surfaces for KU/gap/safety"


@dataclass(frozen=True)
class SafetyReviewListItem:
    queue_item_id: str
    knowledge_unit_id: int
    queue_status: str
    medical_safety_state: str
    high_risk_domain: bool
    reason: Optional[str]
    decision_id: Optional[int]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class ConflictListItem:
    conflict_key: str
    knowledge_unit_id_a: int
    knowledge_unit_id_b: int
    conflict_state: str
    conflict_summary: Optional[str]
    resolution_note: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class KnowledgeGapListItem:
    id: int
    canonical_gap_key: str
    title: str
    domain: str
    status: str
    priority: str
    severity: str
    urgency: str
    next_review_at: Optional[datetime] = None


@dataclass(frozen=True)
class StartSafetyReviewRequest:
    queue_item_id: str
    actor_reference: str


@dataclass(frozen=True)
class CloseSafetyReviewRequest:
    queue_item_id: str
    closed_status: str
    decision_id: int
    reason: str
    actor_reference: str


@dataclass(frozen=True)
class ResolveConflictRequest:
    conflict_key: str
    resolution_note: str
    actor_reference: str


@dataclass(frozen=True)
class TriageGapRequest:
    gap_id: int
    new_status: str
    reviewer_reference: str
    reason: Optional[str] = None
