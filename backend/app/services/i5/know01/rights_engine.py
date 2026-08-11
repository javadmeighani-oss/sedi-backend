"""I5-KNOW-01 Rights Engine — fail-closed multi-dimension rights decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from backend.app.services.i5.enums import (
    ProcessingPermissionMode,
    RawRetentionMode,
    RightDecision,
)


AUTOMATION_CRITICAL_DIMENSIONS = (
    "access_right",
    "automation_right",
    "tdm_right",
    "transform_right",
)


@dataclass(frozen=True)
class RightsDecisionResult:
    allowed: bool
    processing_mode: ProcessingPermissionMode
    raw_retention_mode: RawRetentionMode
    reason: str
    dimensions: Mapping[str, str]


def map_processing_to_raw_retention(mode: ProcessingPermissionMode) -> RawRetentionMode:
    return {
        ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN: RawRetentionMode.RAW_FULL_GOVERNED_RETENTION,
        ProcessingPermissionMode.TRANSIENT_PROCESS_ONLY: RawRetentionMode.RAW_TRANSIENT_PROCESSING,
        ProcessingPermissionMode.DERIVED_KNOWLEDGE_ONLY: RawRetentionMode.RAW_MINIMAL_EVIDENCE_ONLY,
        ProcessingPermissionMode.METADATA_ABSTRACT_ONLY: RawRetentionMode.RAW_LINK_AND_CITATION_ONLY,
        ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED: RawRetentionMode.RAW_EXCLUDED_PROTECTED_ELEMENTS,
        ProcessingPermissionMode.LICENSED_CONNECTOR_ONLY: RawRetentionMode.RAW_EXCLUDED_PROTECTED_ELEMENTS,
    }[mode]


def _norm(value: Optional[str]) -> str:
    return (value or RightDecision.UNKNOWN.value).strip().upper()


def evaluate_automation_rights(
    *,
    access_right: str,
    automation_right: str,
    tdm_right: str,
    transform_right: str,
    retain_raw_right: str,
    retain_derived_right: str,
    redistribution_right: str = RightDecision.UNKNOWN.value,
    robots_state: str = "UNKNOWN",
    processing_permission_mode: Optional[str] = None,
) -> RightsDecisionResult:
    """Fail closed if any automation-critical dimension is UNKNOWN/DENIED/REVIEW_REQUIRED.

    FREE_TO_READ / public URL is never inferred here — callers must set dimensions explicitly.
    """
    dims = {
        "access_right": _norm(access_right),
        "automation_right": _norm(automation_right),
        "tdm_right": _norm(tdm_right),
        "transform_right": _norm(transform_right),
        "retain_raw_right": _norm(retain_raw_right),
        "retain_derived_right": _norm(retain_derived_right),
        "redistribution_right": _norm(redistribution_right),
        "robots_state": _norm(robots_state),
    }

    mode_raw = (processing_permission_mode or ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED.value).strip()
    try:
        mode = ProcessingPermissionMode(mode_raw)
    except ValueError:
        return RightsDecisionResult(
            False,
            ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED,
            RawRetentionMode.RAW_EXCLUDED_PROTECTED_ELEMENTS,
            "INVALID_PROCESSING_MODE",
            dims,
        )

    if mode in {
        ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED,
        ProcessingPermissionMode.LICENSED_CONNECTOR_ONLY,
    }:
        return RightsDecisionResult(
            False, mode, map_processing_to_raw_retention(mode), "MODE_BLOCKS_AUTOMATION", dims
        )

    for key in AUTOMATION_CRITICAL_DIMENSIONS:
        val = dims[key]
        if val in {
            RightDecision.UNKNOWN.value,
            RightDecision.DENIED.value,
            RightDecision.REVIEW_REQUIRED.value,
        }:
            return RightsDecisionResult(
                False,
                mode,
                map_processing_to_raw_retention(mode),
                f"FAIL_CLOSED_{key}_{val}",
                dims,
            )
        if val not in {RightDecision.ALLOWED.value, RightDecision.CONDITIONAL.value}:
            return RightsDecisionResult(
                False, mode, map_processing_to_raw_retention(mode), f"FAIL_CLOSED_{key}_{val}", dims
            )

    if dims["robots_state"] == "DISALLOWED":
        return RightsDecisionResult(
            False, mode, map_processing_to_raw_retention(mode), "ROBOTS_DISALLOWED", dims
        )

    # Retention consistency
    if mode == ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN and dims["retain_raw_right"] != RightDecision.ALLOWED.value:
        return RightsDecisionResult(
            False, mode, map_processing_to_raw_retention(mode), "RETAIN_RAW_NOT_ALLOWED", dims
        )
    if mode == ProcessingPermissionMode.TRANSIENT_PROCESS_ONLY and dims["retain_raw_right"] == RightDecision.ALLOWED.value:
        # Transient forbids durable raw even if somehow marked allowed — force transient semantics
        pass
    if mode in {
        ProcessingPermissionMode.DERIVED_KNOWLEDGE_ONLY,
        ProcessingPermissionMode.METADATA_ABSTRACT_ONLY,
        ProcessingPermissionMode.TRANSIENT_PROCESS_ONLY,
    } and dims["retain_derived_right"] in {
        RightDecision.UNKNOWN.value,
        RightDecision.DENIED.value,
        RightDecision.REVIEW_REQUIRED.value,
    }:
        return RightsDecisionResult(
            False, mode, map_processing_to_raw_retention(mode), "RETAIN_DERIVED_NOT_PERMITTED", dims
        )

    return RightsDecisionResult(True, mode, map_processing_to_raw_retention(mode), "OK", dims)


def assert_no_unauthorized_raw_retention(
    *,
    processing_mode: ProcessingPermissionMode,
    durable_raw_written: bool,
) -> None:
    if durable_raw_written and processing_mode in {
        ProcessingPermissionMode.TRANSIENT_PROCESS_ONLY,
        ProcessingPermissionMode.DERIVED_KNOWLEDGE_ONLY,
        ProcessingPermissionMode.METADATA_ABSTRACT_ONLY,
        ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED,
        ProcessingPermissionMode.LICENSED_CONNECTOR_ONLY,
    }:
        raise PermissionError("UNAUTHORIZED_RAW_RETENTION")
