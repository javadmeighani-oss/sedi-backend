"""SCIS-01 typed retrieval contracts (request/response/provenance)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RetrievalMode(str, Enum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"


class FallbackState(str, Enum):
    NONE = "none"
    LEXICAL_ONLY = "lexical_only"
    VECTOR_ONLY = "vector_only"
    NO_RESULTS = "no_results"
    EMBEDDING_FAILURE = "embedding_failure"
    VECTOR_BACKEND_UNAVAILABLE = "vector_backend_unavailable"
    FTS_FAILURE = "fts_failure"
    NO_ELIGIBLE_KNOWLEDGE = "no_eligible_knowledge"
    PROVENANCE_FAILURE = "provenance_failure"
    BOTH_BRANCHES_UNAVAILABLE = "both_branches_unavailable"


@dataclass(frozen=True)
class ScisRetrievalRequest:
    query_text: str
    query_language: str = "en"
    target_domain: Optional[str] = None
    intent: Optional[str] = None
    safety_classification: Optional[str] = None
    top_k: int = 8
    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID
    allowed_knowledge_classes: tuple[str, ...] = ("GLOBAL_GOVERNED_KNOWLEDGE",)
    request_trace_id: Optional[str] = None
    embedding_model: Optional[str] = None
    user_authorization_context: Optional[Dict[str, Any]] = None  # boundary only; unused for index
    knowledge_filters: Optional[Dict[str, Any]] = None


@dataclass
class ProvenanceRef:
    chunk_id: int
    knowledge_unit_id: Optional[int]
    immutable_version_id: Optional[str]
    raw_evidence_id: Optional[int]
    source_profile_id: Optional[int]
    source_version_id: Optional[str] = None
    locator: Optional[str] = None


@dataclass
class ScisEvidenceItem:
    label: str
    chunk_id: int
    content: str
    language: Optional[str]
    knowledge_unit_id: Optional[int]
    immutable_version_id: Optional[str]
    retrieval_branch: str
    lexical_rank: Optional[int]
    vector_rank: Optional[int]
    fusion_rank: Optional[int]
    fusion_score: Optional[float]
    runtime_eligibility: Optional[str]
    embedding_model: Optional[str]
    embedding_version: Optional[str]
    provenance: ProvenanceRef
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScisRetrievalResponse:
    request_trace_id: Optional[str]
    mode: str
    language: str
    evidence: List[ScisEvidenceItem]
    fallback_state: FallbackState
    timings_ms: Dict[str, float] = field(default_factory=dict)
    candidate_counts: Dict[str, int] = field(default_factory=dict)
    filtered_counts: Dict[str, int] = field(default_factory=dict)
    embedding_model: Optional[str] = None
    embedding_version: Optional[str] = None
    error_class: Optional[str] = None
    observability: Dict[str, Any] = field(default_factory=dict)
