"""Cross-layer KNOW-06 integration matrix (contract expectations; no I6/I7/I8 mutation)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CrossLayerContractRow:
    contract_item: str
    i5_provides: str
    i6_provides: str
    i7_provides: str
    i8_provides: str
    current_status: str
    gap: Optional[str]
    next_owner: str


CROSS_LAYER_MATRIX: tuple[CrossLayerContractRow, ...] = (
    CrossLayerContractRow(
        contract_item="clinical_feature_projection",
        i5_provides="feature_index field contract + lineage rules",
        i6_provides="authorized reads from personal SoTs + projection runtime",
        i7_provides="longitudinal feature enrichment",
        i8_provides="consumes projected features for match",
        current_status="CONTRACT_ONLY",
        gap="no I5/I6 projection runtime table under this Gate",
        next_owner="I6",
    ),
    CrossLayerContractRow(
        contract_item="lineage",
        i5_provides="source_record_type/id mandatory vocabulary",
        i6_provides="stable ids on personal SoTs",
        i7_provides="longitudinal lineage continuity",
        i8_provides="feature_lineage_refs on matches",
        current_status="CONTRACT_ONLY",
        gap="verification_state uneven across SoTs",
        next_owner="I6",
    ),
    CrossLayerContractRow(
        contract_item="consent_privacy_boundary",
        i5_provides="no personal-data write; evidence-only surface",
        i6_provides="consent-gated memory access",
        i7_provides="consent-aware longitudinal use",
        i8_provides="consent-gated recommendation generation",
        current_status="I6_CONSENT_EXISTS; KNOW06_RUNTIME_PENDING",
        gap="KNOW-06 runtime must honor I6 consent; not implemented here",
        next_owner="I6/I8",
    ),
    CrossLayerContractRow(
        contract_item="longitudinal_context",
        i5_provides="criteria vocabulary (disease_duration/stage)",
        i6_provides="care_episodes spine + facts",
        i7_provides="longitudinal user intelligence",
        i8_provides="time-aware applicability",
        current_status="CONTRACT_ONLY",
        gap="I7 integration not under I5 KNOW-06",
        next_owner="I7",
    ),
    CrossLayerContractRow(
        contract_item="evidence_matching",
        i5_provides="user_evidence_matches schema + safe states",
        i6_provides="feature inputs",
        i7_provides="longitudinal match context",
        i8_provides="match runtime + fail-closed safety hook",
        current_status="I8_HOOK_FAIL_CLOSED (GOVERNED_DISEASE_APPLICABILITY_AVAILABLE=False)",
        gap="full match engine + persistence owned outside I5",
        next_owner="I8",
    ),
    CrossLayerContractRow(
        contract_item="contraindication_context",
        i5_provides="contraindication feature + fail-closed statuses",
        i6_provides="allergy/restriction/medication facts",
        i7_provides="longitudinal contraindication signals",
        i8_provides="runtime fail-closed on PRESENT/SUSPECTED",
        current_status="I8_PARTIAL_ALLERGY_RESTRICTION; KNOW06_STATE_CONTRACT",
        gap="no KNOW-06 contraindication_status producer in I5",
        next_owner="I8",
    ),
    CrossLayerContractRow(
        contract_item="safe_applicability_state",
        i5_provides="SAFE_APPLICABILITY_STATES + FORBIDDEN set",
        i6_provides="N/A (context only)",
        i7_provides="N/A (context only)",
        i8_provides="emits only safe states; rejects forbidden",
        current_status="CONTRACT_TESTABLE_IN_I5",
        gap="runtime emitter owned by I8",
        next_owner="I8",
    ),
    CrossLayerContractRow(
        contract_item="recommendation_plan_consumption",
        i5_provides="evidence KU provenance linkage expectations",
        i6_provides="personal constraints",
        i7_provides="longitudinal plan context",
        i8_provides="grounded recommendation / plan actions",
        current_status="I8_EPHEMERAL_SLICE_EXISTS; KNOW06_FULL_PENDING",
        gap="I8 DCR records schema for matches not authorized in this Gate",
        next_owner="I8",
    ),
    CrossLayerContractRow(
        contract_item="notification_handoff_boundary",
        i5_provides="no notification mutation",
        i6_provides="care episode linkage",
        i7_provides="N/A",
        i8_provides="proactive evaluation handoff when applicable",
        current_status="UNCHANGED_BY_THIS_GATE",
        gap=None,
        next_owner="I8/I9_OUT_OF_SCOPE",
    ),
)

RUNTIME_INTEGRATION_GAPS = tuple(
    f"{row.contract_item}:{row.gap}" for row in CROSS_LAYER_MATRIX if row.gap
)
