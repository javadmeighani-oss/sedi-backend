"""NF24 — resolve canonical source rights (CONNECTOR_READY != RIGHTS_ALLOWED)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision
from backend.app.services.i5.know01.rights_engine import evaluate_automation_rights


# Operations evaluated against KNOW-01 dimensions (not inferred from public URL).
OP_NETWORK_FETCH = "NETWORK_FETCH"
OP_DERIVED_METADATA_PERSIST = "DERIVED_METADATA_PERSIST"
OP_RAW_RETENTION = "RAW_RETENTION"
OP_CLINICAL_RUNTIME_PUBLISH = "CLINICAL_RUNTIME_PUBLISH"


@dataclass(frozen=True)
class CanonicalRightsResolution:
    connector_key: str
    canonical_key: Optional[str]
    source_profile_id: Optional[int]
    gsp_found: bool
    extension_found: bool
    registry_state: Optional[str]
    gsp_runtime_eligibility: Optional[str]
    rights_state: str  # RIGHTS_ALLOWED | RIGHTS_BLOCKED | RIGHTS_UNKNOWN
    processing_mode: Optional[str]
    operation: str
    automation_decision: str  # AUTOMATION_ALLOWED | BLOCKED
    storage_decision: str  # DERIVED_GOVERNED_STORE | NO_STORE | RAW_FORBIDDEN
    block_reason: Optional[str]
    dimensions: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "connector_key": self.connector_key,
            "canonical_key": self.canonical_key,
            "source_profile_id": self.source_profile_id,
            "gsp_found": self.gsp_found,
            "extension_found": self.extension_found,
            "registry_state": self.registry_state,
            "gsp_runtime_eligibility": self.gsp_runtime_eligibility,
            "rights_state": self.rights_state,
            "processing_mode": self.processing_mode,
            "operation": self.operation,
            "automation_decision": self.automation_decision,
            "storage_decision": self.storage_decision,
            "block_reason": self.block_reason,
            "dimensions": dict(self.dimensions),
        }


def canonical_key_for_connector(connector_key: str) -> str:
    """KNOW-01 seed identity: know01:{connector_key}."""
    if connector_key.startswith("know01:"):
        return connector_key
    if connector_key.startswith("terminology:"):
        return f"know01:{connector_key}"
    return f"know01:{connector_key}"


def resolve_canonical_source(db: Session, connector_key: str) -> Optional[models.GovernedSourceProfile]:
    """Read-only resolve of canonical GSP. Never creates synthetic product sources."""
    key = canonical_key_for_connector(connector_key)
    row = db.query(models.GovernedSourceProfile).filter_by(canonical_key=key).first()
    if row is not None:
        return row
    # Fallback: connector profile source_profile_key → know01:{key}
    cp = db.query(models.I5ConnectorProfile).filter_by(connector_key=connector_key).first()
    if cp is not None and getattr(cp, "source_profile_key", None):
        alt = f"know01:{cp.source_profile_key}"
        return db.query(models.GovernedSourceProfile).filter_by(canonical_key=alt).first()
    return None


def _classify_rights_state(decision_allowed: bool, dims: dict[str, str], reason: str) -> str:
    if decision_allowed:
        return "RIGHTS_ALLOWED"
    critical = ("access_right", "automation_right", "tdm_right", "transform_right", "retain_derived_right")
    if any(dims.get(k) == RightDecision.UNKNOWN.value for k in critical):
        return "RIGHTS_UNKNOWN"
    if "UNKNOWN" in (reason or "").upper() or reason.startswith("FAIL_CLOSED_") and "UNKNOWN" in reason:
        return "RIGHTS_UNKNOWN"
    return "RIGHTS_BLOCKED"


def evaluate_connector_operation_rights(
    db: Session,
    *,
    connector_key: str,
    operation: str,
) -> CanonicalRightsResolution:
    """Derive operation-specific rights from canonical GSP + registry extension + KNOW-01 engine."""
    gsp = resolve_canonical_source(db, connector_key)
    canon = canonical_key_for_connector(connector_key)
    if gsp is None:
        return CanonicalRightsResolution(
            connector_key=connector_key,
            canonical_key=canon,
            source_profile_id=None,
            gsp_found=False,
            extension_found=False,
            registry_state=None,
            gsp_runtime_eligibility=None,
            rights_state="RIGHTS_UNKNOWN",
            processing_mode=None,
            operation=operation,
            automation_decision="BLOCKED",
            storage_decision="NO_STORE",
            block_reason="CANONICAL_SOURCE_NOT_FOUND",
            dimensions={},
        )

    elig = str(getattr(gsp, "runtime_eligibility", "") or "").upper()
    if elig in {"SUSPENDED", "REVOKED"}:
        return CanonicalRightsResolution(
            connector_key=connector_key,
            canonical_key=gsp.canonical_key,
            source_profile_id=gsp.id,
            gsp_found=True,
            extension_found=False,
            registry_state=getattr(gsp, "registry_state", None),
            gsp_runtime_eligibility=elig,
            rights_state="RIGHTS_BLOCKED",
            processing_mode=None,
            operation=operation,
            automation_decision="BLOCKED",
            storage_decision="NO_STORE",
            block_reason=f"GSP_RUNTIME_{elig}",
            dimensions={},
        )

    ext = db.query(models.I5SourceRegistryExtension).filter_by(source_profile_id=gsp.id).first()
    if ext is None:
        return CanonicalRightsResolution(
            connector_key=connector_key,
            canonical_key=gsp.canonical_key,
            source_profile_id=gsp.id,
            gsp_found=True,
            extension_found=False,
            registry_state=getattr(gsp, "registry_state", None),
            gsp_runtime_eligibility=elig,
            rights_state="RIGHTS_UNKNOWN",
            processing_mode=None,
            operation=operation,
            automation_decision="BLOCKED",
            storage_decision="NO_STORE",
            block_reason="REGISTRY_EXTENSION_MISSING",
            dimensions={},
        )

    decision = evaluate_automation_rights(
        access_right=ext.access_right,
        automation_right=ext.automation_right,
        tdm_right=ext.tdm_right,
        transform_right=ext.transform_right,
        retain_raw_right=ext.retain_raw_right,
        retain_derived_right=ext.retain_derived_right,
        redistribution_right=ext.redistribution_right,
        robots_state=ext.robots_state or "UNKNOWN",
        processing_permission_mode=ext.processing_permission_mode,
    )
    dims = dict(decision.dimensions)
    rights_state = _classify_rights_state(decision.allowed, dims, decision.reason)

    # Operation-specific overlays (do not require irrelevant permissions beyond engine).
    storage = "NO_STORE"
    auto = "BLOCKED"
    block = decision.reason if not decision.allowed else None

    if operation == OP_NETWORK_FETCH:
        # Network fetch still fail-closed on UNKNOWN/DENIED automation-critical dims.
        if decision.allowed and rights_state == "RIGHTS_ALLOWED":
            auto = "AUTOMATION_ALLOWED"
            block = None
        else:
            auto = "BLOCKED"
            block = block or f"NETWORK_FETCH_{rights_state}"
        storage = "NO_STORE"

    elif operation == OP_DERIVED_METADATA_PERSIST:
        if rights_state != "RIGHTS_ALLOWED" or not decision.allowed:
            auto = "BLOCKED"
            storage = "NO_STORE"
            block = block or f"DERIVED_PERSIST_{rights_state}"
        elif dims.get("retain_derived_right") != RightDecision.ALLOWED.value:
            auto = "BLOCKED"
            storage = "NO_STORE"
            block = "RETAIN_DERIVED_NOT_ALLOWED"
            rights_state = "RIGHTS_BLOCKED" if dims.get("retain_derived_right") == RightDecision.DENIED.value else "RIGHTS_UNKNOWN"
        elif decision.processing_mode.value not in {
            ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
            ProcessingPermissionMode.DERIVED_KNOWLEDGE_ONLY.value,
            ProcessingPermissionMode.TRANSIENT_PROCESS_ONLY.value,
            ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN.value,
        }:
            auto = "BLOCKED"
            storage = "NO_STORE"
            block = f"PROCESSING_MODE_BLOCKS_DERIVED:{decision.processing_mode.value}"
        else:
            auto = "AUTOMATION_ALLOWED"
            storage = "DERIVED_GOVERNED_STORE"
            block = None

    elif operation == OP_RAW_RETENTION:
        if dims.get("retain_raw_right") == RightDecision.ALLOWED.value and decision.allowed:
            auto = "AUTOMATION_ALLOWED"
            storage = "RAW_GOVERNED_STORE"
            block = None
        else:
            auto = "BLOCKED"
            storage = "RAW_FORBIDDEN"
            block = "RAW_RETENTION_NOT_ALLOWED"

    elif operation == OP_CLINICAL_RUNTIME_PUBLISH:
        # Clinical runtime publish requires allowed automation + not blocked mode.
        if rights_state == "RIGHTS_ALLOWED" and decision.allowed:
            auto = "AUTOMATION_ALLOWED"
            storage = "DERIVED_GOVERNED_STORE"
            block = None
        else:
            auto = "BLOCKED"
            storage = "NO_STORE"
            block = block or f"CLINICAL_PUBLISH_{rights_state}"
    else:
        block = f"UNKNOWN_OPERATION:{operation}"

    # Hard rule: UNKNOWN rights → no automated persist/publish
    if rights_state == "RIGHTS_UNKNOWN" and operation in {
        OP_DERIVED_METADATA_PERSIST,
        OP_RAW_RETENTION,
        OP_CLINICAL_RUNTIME_PUBLISH,
    }:
        auto = "BLOCKED"
        storage = "NO_STORE" if operation != OP_RAW_RETENTION else "RAW_FORBIDDEN"
        block = block or "UNKNOWN_RIGHTS_NO_AUTOMATED_PERSIST"

    return CanonicalRightsResolution(
        connector_key=connector_key,
        canonical_key=gsp.canonical_key,
        source_profile_id=gsp.id,
        gsp_found=True,
        extension_found=True,
        registry_state=getattr(gsp, "registry_state", None),
        gsp_runtime_eligibility=elig,
        rights_state=rights_state,
        processing_mode=decision.processing_mode.value,
        operation=operation,
        automation_decision=auto,
        storage_decision=storage,
        block_reason=block,
        dimensions=dims,
    )


def count_synthetic_product_rights_sources(db: Session) -> int:
    """Product-path synthetic rehearsal GSPs must be zero."""
    return (
        db.query(models.GovernedSourceProfile)
        .filter(models.GovernedSourceProfile.canonical_key.like("know05:rehearsal:%"))
        .count()
    )
