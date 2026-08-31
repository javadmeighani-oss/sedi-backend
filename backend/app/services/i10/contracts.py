"""I10 bounded notification candidate contract — references only, no raw health/RAG/chat."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from backend.app.services.i10.policy_types import (
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)

# Fields that must never appear on an I10 candidate payload.
_FORBIDDEN_CANDIDATE_KEYS = frozenset(
    {
        "numeric_value",
        "raw_value",
        "packet_body",
        "packet_payload",
        "measurement_value",
        "embedding",
        "embedding_vector",
        "rag_chunk",
        "chunk_text",
        "user_message",
        "sedi_response",
        "transcript",
        "diagnosis",
        "clinical_threshold",
    }
)

# Architecture guard: I10 must not import live RAG retrieval modules.
I10_RAG_IMPORT_BLOCKLIST = frozenset(
    {
        "backend.app.services.notification_runtime.rag_provider",
        "backend.app.services.rag",
        "backend.app.services.i5.runtime_knowledge_retrieval",
        "backend.app.services.scis.retrieval",
    }
)


@dataclass(frozen=True)
class I10NotificationCandidate:
    """Bounded upstream signal for I10 policy — not notification copy."""

    candidate_key: str
    health_subject_id: int
    recipient_user_id: int
    notification_scope: I10NotificationScope
    source_owner: str
    source_type: str
    source_id: str
    semantic_family: I10SemanticFamily
    source_version: Optional[str] = None
    priority_hint: Optional[str] = None
    privacy_hint: I10PrivacyClass = I10PrivacyClass.PRIVATE
    valid_from: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    knowledge_refs: Sequence[str] = field(default_factory=tuple)
    provenance_refs: Sequence[str] = field(default_factory=tuple)
    user_caregiver_id: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.candidate_key or not self.candidate_key.strip():
            raise ValueError("I10_CANDIDATE_KEY_REQUIRED")
        if self.health_subject_id <= 0:
            raise ValueError("I10_HEALTH_SUBJECT_REQUIRED")
        if self.recipient_user_id <= 0:
            raise ValueError("I10_RECIPIENT_REQUIRED")
        for ref in self.knowledge_refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("I10_KNOWLEDGE_REF_INVALID")
        for ref in self.provenance_refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("I10_PROVENANCE_REF_INVALID")

    def provenance_refs_json(self) -> str:
        payload = {
            "knowledge_refs": list(self.knowledge_refs),
            "provenance_refs": list(self.provenance_refs),
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def reject_forbidden_candidate_fields(mapping: Mapping[str, Any]) -> None:
    """Fail closed if a producer attempts to pass raw health/RAG/chat fields."""
    for key in mapping:
        normalized = key.lower()
        if normalized in _FORBIDDEN_CANDIDATE_KEYS:
            raise ValueError(f"I10_FORBIDDEN_CANDIDATE_FIELD:{key}")
        if normalized.startswith("raw_"):
            raise ValueError(f"I10_FORBIDDEN_CANDIDATE_FIELD:{key}")


def assert_no_live_rag_import(module_name: str) -> None:
    if module_name in I10_RAG_IMPORT_BLOCKLIST:
        raise ImportError(f"I10_DIRECT_RAG_IMPORT_PROHIBITED:{module_name}")
