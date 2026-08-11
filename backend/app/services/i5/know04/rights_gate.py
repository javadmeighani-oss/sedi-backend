"""Connector rights gate — NO_STORAGE != NO_PROCESSING; UNKNOWN fails closed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision
from backend.app.services.i5.know01.rights_engine import evaluate_automation_rights
from backend.app.services.i5.know04.contract import ConnectorRecord


@dataclass(frozen=True)
class ConnectorRightsDecision:
    discovery_allowed: bool
    automated_retrieval_allowed: bool
    transient_processing_allowed: bool
    raw_storage_allowed: bool
    full_text_storage_allowed: bool
    derived_fact_storage_allowed: bool
    embedding_allowed: bool
    redistribution_allowed: bool
    processing_decision: str
    storage_decision: str
    reasons: tuple[str, ...]


def evaluate_connector_rights(
    *,
    processing_mode: str,
    access_right: str = RightDecision.UNKNOWN.value,
    automation_right: str = RightDecision.UNKNOWN.value,
    tdm_right: str = RightDecision.UNKNOWN.value,
    transform_right: str = RightDecision.UNKNOWN.value,
    retain_raw_right: str = RightDecision.UNKNOWN.value,
    retain_derived_right: str = RightDecision.UNKNOWN.value,
    redistribute_right: str = RightDecision.UNKNOWN.value,
    robots_state: str = "UNKNOWN",
    full_text_explicitly_allowed: bool = False,
    embedding_explicitly_allowed: bool = False,
) -> ConnectorRightsDecision:
    result = evaluate_automation_rights(
        processing_permission_mode=processing_mode,
        access_right=access_right,
        automation_right=automation_right,
        tdm_right=tdm_right,
        transform_right=transform_right,
        retain_raw_right=retain_raw_right,
        retain_derived_right=retain_derived_right,
        redistribution_right=redistribute_right,
        robots_state=robots_state,
    )
    reasons = (result.reason,)
    unknown_block = (
        (not result.allowed)
        or result.reason.startswith("FAIL_CLOSED_")
        or "UNKNOWN" in result.reason
        or result.reason in {"MODE_BLOCKS_AUTOMATION", "INVALID_PROCESSING_MODE"}
    )

    discovery = access_right == RightDecision.ALLOWED.value and not unknown_block
    retrieval = automation_right == RightDecision.ALLOWED.value and result.allowed
    transient = processing_mode in {
        ProcessingPermissionMode.TRANSIENT_PROCESS_ONLY.value,
        ProcessingPermissionMode.DERIVED_KNOWLEDGE_ONLY.value,
        ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
        ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN.value,
    } and result.allowed
    raw_store = (
        retain_raw_right == RightDecision.ALLOWED.value
        and processing_mode == ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN.value
        and result.allowed
    )
    full_text = full_text_explicitly_allowed and raw_store
    derived = retain_derived_right == RightDecision.ALLOWED.value and result.allowed
    embedding = False  # NEVER infer embedding; require explicit allow AND no unknown
    if embedding_explicitly_allowed and derived and not unknown_block:
        embedding = True
    redistribute = redistribute_right == RightDecision.ALLOWED.value and not unknown_block

    if unknown_block or not result.allowed:
        proc = "BLOCK"
        store = "NO_STORE"
    elif raw_store:
        proc = "PROCESS"
        store = "RAW_RETAIN"
    elif transient and derived:
        proc = "TRANSIENT_PROCESS"
        store = "TRANSIENT_THEN_DELETE"
    elif processing_mode == ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value and result.allowed:
        proc = "METADATA_ONLY"
        store = "DERIVED_ONLY"
    elif derived:
        proc = "TRANSIENT_PROCESS"
        store = "DERIVED_ONLY"
    else:
        proc = "BLOCK"
        store = "NO_STORE"

    return ConnectorRightsDecision(
        discovery_allowed=discovery and not unknown_block,
        automated_retrieval_allowed=retrieval,
        transient_processing_allowed=transient and proc != "BLOCK",
        raw_storage_allowed=raw_store,
        full_text_storage_allowed=full_text,
        derived_fact_storage_allowed=derived and proc != "BLOCK",
        embedding_allowed=embedding,
        redistribution_allowed=redistribute,
        processing_decision=proc,
        storage_decision=store,
        reasons=reasons,
    )


def require_processing_allowed(decision: ConnectorRightsDecision) -> None:
    if decision.processing_decision == "BLOCK":
        raise PermissionError("PROCESSING_BLOCK:" + ",".join(decision.reasons))
    if any("UNKNOWN" in r or "FAIL_CLOSED_" in r for r in decision.reasons):
        raise PermissionError("UNKNOWN_RIGHTS_AUTOMATION")


def apply_rights_to_record(record: ConnectorRecord, decision: ConnectorRightsDecision) -> ConnectorRecord:
    record.processing_decision = decision.processing_decision
    record.storage_decision = decision.storage_decision
    return record


def assert_no_phi_in_request(params: Mapping[str, Any]) -> None:
    banned = {"user_id", "patient_id", "phi", "national_id", "ssn", "phone", "email_user"}
    for k in params:
        if str(k).lower() in banned:
            raise PermissionError("USER_PHI_SENT_TO_SCIENTIFIC_CONNECTORS")
