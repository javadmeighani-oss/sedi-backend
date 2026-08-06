"""I5-IMPL-W2-P01 — pure supersession / structured-diff helpers (no DB required).

ORM mutation helpers accept an optional Session and stay thin.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Sequence, Union

from backend.app.services.i5.enums import MemoryChangeKind, MemoryTransitionKind

_FIELD_SEP = "\x1f"

_CONTENT_FIELDS: tuple[str, ...] = (
    "normalized_statement",
    "canonical_hash",
    "applicability",
    "exclusions",
)

_SAFETY_GOVERNANCE_FIELDS: tuple[str, ...] = (
    "evidence_strength",
    "medical_safety_state",
    "conflict_state",
    "freshness_state",
    "publication_state",
    "runtime_eligibility",
    "retraction_reason",
)

_SOURCE_METADATA_FIELDS: tuple[str, ...] = (
    "source_document_id",
    "source_version_id",
    "source_profile_id",
    "canonical_url",
)

_PROVENANCE_FIELDS: tuple[str, ...] = (
    "provenance_complete",
    "content_hash",
    "byte_hash",
    "normalized_hash",
    "retrieval_method",
    "attribution_data",
)

_COMPARE_FIELDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        _CONTENT_FIELDS
        + _SAFETY_GOVERNANCE_FIELDS
        + _SOURCE_METADATA_FIELDS
        + _PROVENANCE_FIELDS
    )
)


class SupersessionServiceError(ValueError):
    """Fail-closed validation error for supersession helpers."""


def sha256_hex(payload: str) -> str:
    """Return lowercase SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_mapping(obj: Union[Mapping[str, Any], Any]) -> Mapping[str, Any]:
    if isinstance(obj, Mapping):
        return obj
    return {field: getattr(obj, field, None) for field in _COMPARE_FIELDS} | {
        "id": getattr(obj, "id", None),
        "canonical_unit_id": getattr(obj, "canonical_unit_id", None),
        "supersedes_unit_id": getattr(obj, "supersedes_unit_id", None),
        "immutable_version_id": getattr(obj, "immutable_version_id", None),
    }


def _norm_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def detect_change_kind(
    old_ku: Union[Mapping[str, Any], Any],
    new_ku: Union[Mapping[str, Any], Any],
) -> MemoryChangeKind:
    """Classify the material change between two knowledge-unit snapshots."""
    old = _as_mapping(old_ku)
    new = _as_mapping(new_ku)

    old_retraction = _norm_value(old.get("retraction_reason"))
    new_retraction = _norm_value(new.get("retraction_reason"))
    old_pub = _norm_value(old.get("publication_state"))
    new_pub = _norm_value(new.get("publication_state"))
    if (new_retraction and new_retraction != old_retraction) or (
        new_pub == "WITHDRAWN" and new_pub != old_pub
    ):
        return MemoryChangeKind.RETRACTION_WITHDRAWAL

    if any(_norm_value(old.get(f)) != _norm_value(new.get(f)) for f in _CONTENT_FIELDS):
        return MemoryChangeKind.CONTENT_CHANGE

    if any(
        _norm_value(old.get(f)) != _norm_value(new.get(f)) for f in _SAFETY_GOVERNANCE_FIELDS
    ):
        return MemoryChangeKind.SAFETY_GOVERNANCE_CHANGE

    if any(_norm_value(old.get(f)) != _norm_value(new.get(f)) for f in _PROVENANCE_FIELDS):
        return MemoryChangeKind.PROVENANCE_CHANGE

    if any(
        _norm_value(old.get(f)) != _norm_value(new.get(f)) for f in _SOURCE_METADATA_FIELDS
    ):
        return MemoryChangeKind.SOURCE_METADATA_CHANGE

    return MemoryChangeKind.NO_MATERIAL_CHANGE


def compute_structured_diff(
    old_ku: Union[Mapping[str, Any], Any],
    new_ku: Union[Mapping[str, Any], Any],
) -> dict[str, Any]:
    """Return changed_fields, change_kind, and field_diffs for two KU snapshots."""
    old = _as_mapping(old_ku)
    new = _as_mapping(new_ku)
    field_diffs: dict[str, dict[str, Any]] = {}
    for field in _COMPARE_FIELDS:
        old_val = _norm_value(old.get(field))
        new_val = _norm_value(new.get(field))
        if old_val != new_val:
            field_diffs[field] = {"old": old_val, "new": new_val}
    changed_fields = sorted(field_diffs.keys())
    change_kind = detect_change_kind(old, new)
    return {
        "changed_fields": changed_fields,
        "change_kind": change_kind.value,
        "field_diffs": field_diffs,
    }


def build_idempotency_key(
    memory_item_id: str,
    canonical_hash: str,
    change_kind: Union[str, MemoryChangeKind],
    process_nonce: str = "",
) -> str:
    """Deterministic SHA-256 idempotency key for a memory transition."""
    kind = change_kind.value if isinstance(change_kind, MemoryChangeKind) else str(change_kind)
    parts = (
        str(memory_item_id).strip(),
        str(canonical_hash).strip(),
        kind.strip(),
        str(process_nonce).strip(),
    )
    return sha256_hex(_FIELD_SEP.join(parts))


def validate_supersession_link(
    new_ku: Union[Mapping[str, Any], Any],
    old_ku: Union[Mapping[str, Any], Any],
) -> None:
    """Fail-closed validation for new→old supersession linkage."""
    new = _as_mapping(new_ku)
    old = _as_mapping(old_ku)
    new_id = new.get("id")
    old_id = old.get("id")
    if new_id is not None and old_id is not None and new_id == old_id:
        raise SupersessionServiceError("SUPERSESSION_SELF_PARENT_REFUSED")
    new_canon = _norm_value(new.get("canonical_unit_id"))
    old_canon = _norm_value(old.get("canonical_unit_id"))
    if new_canon != old_canon:
        raise SupersessionServiceError("SUPERSESSION_CROSS_CANONICAL_REFUSED")
    link = new.get("supersedes_unit_id")
    if link is not None and old_id is not None and link != old_id:
        raise SupersessionServiceError("SUPERSESSION_LINK_MISMATCH")


def resolve_superseded_by(
    units_by_supersedes: Mapping[int, Sequence[int]],
    unit_id: int,
) -> list[int]:
    """Inverse of KnowledgeUnit.supersedes_unit_id (new→old): who supersedes unit_id."""
    return list(units_by_supersedes.get(unit_id, ()))


def apply_no_change_result(
    *,
    memory_item_id: str,
    canonical_hash: str,
    process_nonce: str = "",
) -> dict[str, Any]:
    """Build a NO_CHANGE transition payload (no duplicate memory row implied)."""
    change_kind = MemoryChangeKind.NO_MATERIAL_CHANGE
    return {
        "transition_kind": MemoryTransitionKind.NO_CHANGE.value,
        "change_kind": change_kind.value,
        "idempotency_key": build_idempotency_key(
            memory_item_id, canonical_hash, change_kind, process_nonce
        ),
        "diff_json": None,
    }


def structured_diff_to_json(diff: Mapping[str, Any]) -> str:
    """Serialize a structured diff dict to a JSON object string."""
    return json.dumps(dict(diff), sort_keys=True, separators=(",", ":"))


def record_transition_fields(
    *,
    memory_row_id: int,
    memory_item_id: str,
    transition_kind: Union[str, MemoryTransitionKind],
    change_kind: Union[str, MemoryChangeKind],
    idempotency_key: str,
    from_knowledge_unit_id: Optional[int] = None,
    to_knowledge_unit_id: Optional[int] = None,
    diff_json: Optional[str] = None,
    reason: Optional[str] = None,
    process_id: str = "W2P01_SUPERSESSION_SERVICE",
) -> dict[str, Any]:
    """Thin field dict for KnowledgeMemoryTransition construction / ORM insert."""
    return {
        "memory_row_id": memory_row_id,
        "memory_item_id": memory_item_id,
        "from_knowledge_unit_id": from_knowledge_unit_id,
        "to_knowledge_unit_id": to_knowledge_unit_id,
        "transition_kind": (
            transition_kind.value
            if isinstance(transition_kind, MemoryTransitionKind)
            else str(transition_kind)
        ),
        "change_kind": (
            change_kind.value if isinstance(change_kind, MemoryChangeKind) else str(change_kind)
        ),
        "diff_json": diff_json,
        "idempotency_key": idempotency_key,
        "reason": reason,
        "process_id": process_id,
    }
