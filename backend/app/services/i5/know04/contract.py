"""Normalized connector contract — sources implement only meaningful methods."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Protocol


@dataclass(frozen=True)
class ConnectorCapabilities:
    discover: bool = False
    fetch_metadata: bool = False
    fetch_record: bool = False
    fetch_changes: bool = False
    fetch_related: bool = False
    classify_rights: bool = True
    normalize: bool = True
    emit_artifact_candidate: bool = True
    emit_change_event: bool = True


@dataclass
class ConnectorRecord:
    source_identity: str
    source_role: str
    official_authority: str
    resource_type: str
    external_identifier: str
    canonical_locator: Optional[str] = None
    version_revision: Optional[str] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    content_hash: Optional[str] = None
    license_observation: Optional[str] = None
    processing_decision: str = "BLOCK"
    storage_decision: str = "NO_STORE"
    change_state: Optional[str] = None
    retraction_state: Optional[str] = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    payload: Mapping[str, Any] = field(default_factory=dict)
    synthetic_fixture: bool = False


class ScientificConnector(Protocol):
    connector_key: str
    capabilities: ConnectorCapabilities

    def classify_rights(self, record: Optional[ConnectorRecord] = None) -> Mapping[str, Any]:
        ...

    def normalize(self, raw: Mapping[str, Any]) -> ConnectorRecord:
        ...
