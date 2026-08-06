"""I5-IMPL-W1-P02 — pure provenance validation helpers (no DB)."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional, Union


class ProvenanceServiceError(ValueError):
    """Fail-closed validation error for provenance helpers."""


_REQUIRED_COMPLETE_FIELDS: tuple[str, ...] = (
    "knowledge_unit_id",
    "source_profile_id",
    "retrieval_method",
)


def _field(obj: Union[Mapping[str, Any], Any], name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def is_provenance_complete(provenance: Union[Mapping[str, Any], Any]) -> bool:
    """Require knowledge_unit_id, source_profile_id, and non-empty retrieval_method."""
    ku_id = _field(provenance, "knowledge_unit_id")
    source_id = _field(provenance, "source_profile_id")
    method = _field(provenance, "retrieval_method")
    if ku_id is None or source_id is None:
        return False
    try:
        if int(ku_id) <= 0 or int(source_id) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    if method is None:
        return False
    if not str(method).strip():
        return False
    return True


def require_provenance_complete(provenance: Union[Mapping[str, Any], Any]) -> None:
    """Raise if provenance fails the completeness gate."""
    if not is_provenance_complete(provenance):
        raise ProvenanceServiceError("PROVENANCE_INCOMPLETE")


def attach_hash_lineage(
    target: MutableMapping[str, Any],
    *,
    content_hash: Optional[str] = None,
    byte_hash: Optional[str] = None,
    normalized_hash: Optional[str] = None,
) -> MutableMapping[str, Any]:
    """Attach optional SHA-256 lineage hashes onto a provenance payload dict."""
    if content_hash is not None:
        target["content_hash"] = content_hash
    if byte_hash is not None:
        target["byte_hash"] = byte_hash
    if normalized_hash is not None:
        target["normalized_hash"] = normalized_hash
    return target


def build_hash_lineage_dict(
    *,
    content_hash: Optional[str] = None,
    byte_hash: Optional[str] = None,
    normalized_hash: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Return a new hash-lineage mapping (exact_hash_lineage contract helper)."""
    return {
        "content_hash": content_hash,
        "byte_hash": byte_hash,
        "normalized_hash": normalized_hash,
    }


def missing_completeness_fields(
    provenance: Union[Mapping[str, Any], Any],
) -> tuple[str, ...]:
    """List required completeness fields that are missing or empty."""
    missing: list[str] = []
    for name in _REQUIRED_COMPLETE_FIELDS:
        value = _field(provenance, name)
        if name == "retrieval_method":
            if value is None or not str(value).strip():
                missing.append(name)
            continue
        if value is None:
            missing.append(name)
            continue
        try:
            if int(value) <= 0:
                missing.append(name)
        except (TypeError, ValueError):
            missing.append(name)
    return tuple(missing)
