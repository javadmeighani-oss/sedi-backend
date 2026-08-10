"""Provenance assembly for SCIS results."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.app.services.scis.contracts import ProvenanceRef


def build_provenance(payload: Mapping[str, Any]) -> ProvenanceRef:
    return ProvenanceRef(
        chunk_id=int(payload["chunk_id"]),
        knowledge_unit_id=_opt_int(payload.get("knowledge_unit_id")),
        immutable_version_id=_opt_str(payload.get("immutable_version_id")),
        raw_evidence_id=_opt_int(payload.get("raw_evidence_id")),
        source_profile_id=_opt_int(payload.get("source_profile_id")),
        source_version_id=_opt_str(payload.get("source_version_id")),
        locator=_opt_str(payload.get("section_path")) or _opt_str(payload.get("search_document")),
    )


def provenance_complete_for_accepted(payload: Mapping[str, Any]) -> bool:
    """Accepted results must not be orphaned from KU when KU-linked."""
    ku_id = payload.get("knowledge_unit_id")
    if ku_id is None:
        # Gate3-only chunks without KU are allowed only if explicitly non-KU fixtures;
        # SCIS-01 governed path requires KU linkage.
        return False
    if not payload.get("immutable_version_id"):
        return False
    # source_profile may be null in synthetic fixtures; require KU id + version at minimum
    return True


def _opt_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    return int(v)


def _opt_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s if s else None
