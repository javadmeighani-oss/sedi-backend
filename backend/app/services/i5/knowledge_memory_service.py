"""I5-IMPL-W2-P01 — pure Knowledge Memory helpers (no DB required).

Memory-item identity, path refusal, eligibility projection from knowledge units.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional, Union

from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility, SupersessionState

_FIELD_SEP = "\x1f"

_REFUSED_PATH_MARKERS: tuple[str, ...] = (
    "user_memory",
    "local_rag",
    "conversation",
)


class KnowledgeMemoryServiceError(ValueError):
    """Fail-closed validation error for knowledge-memory helpers."""


def sha256_hex(payload: str) -> str:
    """Return lowercase SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _norm(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_memory_item_id(domain: str, topic: str, canonical_unit_id: str) -> str:
    """Deterministic logical memory-item id (SHA-256 hex)."""
    parts = (_norm(domain), _norm(topic), _norm(canonical_unit_id))
    return sha256_hex(_FIELD_SEP.join(parts))


def assert_not_user_memory_path(path: str) -> None:
    """Refuse paths that contain user_memory / local_rag / conversation markers."""
    if path is None:
        raise KnowledgeMemoryServiceError("USER_MEMORY_PATH_REFUSED:null_path")
    sample = str(path).replace("\\", "/").lower()
    for marker in _REFUSED_PATH_MARKERS:
        if marker in sample:
            raise KnowledgeMemoryServiceError(f"USER_MEMORY_PATH_REFUSED:{marker}")


def _as_mapping(obj: Union[Mapping[str, Any], Any]) -> Mapping[str, Any]:
    if isinstance(obj, Mapping):
        return obj
    keys = (
        "supersession_state",
        "runtime_eligibility",
        "domain",
        "topic",
        "topic_taxonomy",
        "canonical_unit_id",
        "immutable_version_id",
        "knowledge_version",
        "source_ids",
        "source_versions",
        "evidence_strength",
        "freshness_state",
        "conflict_state",
        "medical_safety_state",
        "id",
        "knowledge_unit_id",
        "memory_item_id",
    )
    return {k: getattr(obj, k, None) for k in keys}


def evaluate_memory_eligibility(
    mapping: Union[Mapping[str, Any], Any],
) -> KnowledgeUnitRuntimeEligibility:
    """Fail-closed: ELIGIBLE only when supersession_state is CURRENT and field says ELIGIBLE."""
    data = _as_mapping(mapping)
    supersession = str(data.get("supersession_state") or "")
    runtime = str(data.get("runtime_eligibility") or "")
    if supersession != SupersessionState.CURRENT.value:
        return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    if runtime != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
        try:
            return KnowledgeUnitRuntimeEligibility(runtime)
        except ValueError:
            return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    return KnowledgeUnitRuntimeEligibility.ELIGIBLE


def project_from_knowledge_unit(ku: Union[Mapping[str, Any], Any]) -> dict[str, Any]:
    """Project a knowledge-unit mapping into knowledge-memory field dict (no DB)."""
    data = _as_mapping(ku)
    domain = _norm(data.get("domain")) or "unknown"
    topic = _norm(data.get("topic")) or _norm(data.get("topic_taxonomy"))
    canonical_unit_id = _norm(data.get("canonical_unit_id"))
    knowledge_version = _norm(data.get("immutable_version_id")) or _norm(
        data.get("knowledge_version")
    )
    ku_id = data.get("id")
    if ku_id is None:
        ku_id = data.get("knowledge_unit_id")
    memory_item_id = data.get("memory_item_id") or build_memory_item_id(
        domain, topic, canonical_unit_id
    )
    runtime_raw = data.get("runtime_eligibility") or KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    supersession_raw = data.get("supersession_state") or SupersessionState.CURRENT.value
    projected = {
        "memory_item_id": memory_item_id,
        "knowledge_unit_id": ku_id,
        "domain": domain,
        "topic": topic or None,
        "knowledge_version": knowledge_version,
        "source_ids": data.get("source_ids"),
        "source_versions": data.get("source_versions"),
        "evidence_strength": data.get("evidence_strength") or "UNKNOWN",
        "freshness_state": data.get("freshness_state") or "UNKNOWN",
        "conflict_state": data.get("conflict_state") or "NONE",
        "medical_safety_state": data.get("medical_safety_state") or "UNKNOWN",
        "runtime_eligibility": str(runtime_raw),
        "supersession_state": str(supersession_raw),
    }
    # Fail-closed eligibility projection for runtime consumers.
    elig = evaluate_memory_eligibility(projected)
    if elig is not KnowledgeUnitRuntimeEligibility.ELIGIBLE:
        if projected["runtime_eligibility"] == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
            projected["runtime_eligibility"] = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    return projected
