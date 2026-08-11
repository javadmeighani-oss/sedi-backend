"""Transient raw processing — RAW_STORAGE denied still allows permitted derived persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, MutableMapping, Optional

from backend.app.services.i5.know04.rights_gate import ConnectorRightsDecision, require_processing_allowed


@dataclass
class TransientRawWorkspace:
    """In-memory only. Must prove TRANSIENT_RAW_RESIDUE=0 after close."""

    _raw: Optional[bytes] = None
    _derived: MutableMapping[str, Any] = field(default_factory=dict)
    closed: bool = False

    def load(self, raw: bytes, decision: ConnectorRightsDecision) -> None:
        require_processing_allowed(decision)
        if decision.raw_storage_allowed:
            raise PermissionError("USE_GOVERNED_RAW_STORE_NOT_TRANSIENT")
        if not decision.transient_processing_allowed and decision.processing_decision not in {
            "TRANSIENT_PROCESS",
            "METADATA_ONLY",
        }:
            raise PermissionError("PROCESSING_BLOCK")
        self._raw = raw
        self.closed = False

    def derive(self, key: str, value: Any, decision: ConnectorRightsDecision) -> None:
        if self.closed or self._raw is None:
            raise RuntimeError("TRANSIENT_WORKSPACE_EMPTY")
        if not decision.derived_fact_storage_allowed:
            raise PermissionError("DERIVED_FACT_STORAGE_DENIED")
        self._derived[key] = value

    def close_and_delete_raw(self) -> dict[str, Any]:
        self._raw = None
        derived = dict(self._derived)
        self._derived.clear()
        self.closed = True
        return derived

    @property
    def raw_residue_bytes(self) -> int:
        return 0 if self._raw is None else len(self._raw)
