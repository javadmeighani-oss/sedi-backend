"""Governed publication pipeline — PIPELINE_STAGE != POLICY_DECISION (NF23)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    GovernanceDecisionOutcome,
    GovernanceDecisionType,
    GovernanceEntityType,
    MedicalSafetyState,
)


class PublicationStage(str, Enum):
    RAW_SOURCE_RECORD = "RAW_SOURCE_RECORD"
    NORMALIZED_CANDIDATE = "NORMALIZED_CANDIDATE"
    STRUCTURED_EXTRACTION = "STRUCTURED_EXTRACTION"
    VALIDATION = "VALIDATION"
    EVIDENCE_LINKING = "EVIDENCE_LINKING"
    CONFLICT_CHECK = "CONFLICT_CHECK"
    MEDICAL_SAFETY_CHECK = "MEDICAL_SAFETY_CHECK"
    GOVERNANCE_DECISION = "GOVERNANCE_DECISION"
    RUNTIME_ELIGIBILITY = "RUNTIME_ELIGIBILITY"


_STAGE_ORDER = list(PublicationStage)


class PublicationPipelineError(ValueError):
    pass


@dataclass
class PublicationGateEvidence:
    """Proven inputs for gates — never inferred from stage position alone."""

    provenance_complete: bool = False
    evidence_linked: bool = False
    conflict_clear: bool = False
    safety_clear: bool = False
    governance_approved: bool = False
    clinical_runtime_allowed: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provenance_complete": self.provenance_complete,
            "evidence_linked": self.evidence_linked,
            "conflict_clear": self.conflict_clear,
            "safety_clear": self.safety_clear,
            "governance_approved": self.governance_approved,
            "clinical_runtime_allowed": self.clinical_runtime_allowed,
            "notes": list(self.notes),
        }


@dataclass
class PublicationCandidate:
    external_identifier: str
    source_connector_key: str
    stage: PublicationStage = PublicationStage.RAW_SOURCE_RECORD
    model_extracted: bool = False
    provenance_complete: bool = False
    evidence_linked: bool = False
    conflict_clear: bool = False
    safety_clear: bool = False
    governance_approved: bool = False
    runtime_eligible: bool = False
    artifact_type: Optional[str] = None
    knowledge_type: Optional[str] = None
    medical_safety_state: str = MedicalSafetyState.UNKNOWN.value
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "external_identifier": self.external_identifier,
            "source_connector_key": self.source_connector_key,
            "stage": self.stage.value,
            "model_extracted": self.model_extracted,
            "provenance_complete": self.provenance_complete,
            "evidence_linked": self.evidence_linked,
            "conflict_clear": self.conflict_clear,
            "safety_clear": self.safety_clear,
            "governance_approved": self.governance_approved,
            "runtime_eligible": self.runtime_eligible,
            "artifact_type": self.artifact_type,
            "knowledge_type": self.knowledge_type,
            "medical_safety_state": self.medical_safety_state,
            "notes": list(self.notes),
        }


def apply_proven_gates(candidate: PublicationCandidate, evidence: PublicationGateEvidence) -> PublicationCandidate:
    """Copy only proven gate flags onto the candidate (no fabrication)."""
    candidate.provenance_complete = bool(evidence.provenance_complete)
    candidate.evidence_linked = bool(evidence.evidence_linked)
    candidate.conflict_clear = bool(evidence.conflict_clear)
    candidate.safety_clear = bool(evidence.safety_clear)
    candidate.governance_approved = bool(evidence.governance_approved)
    candidate.notes.extend(evidence.notes)
    return candidate


def advance_stage(candidate: PublicationCandidate, to_stage: PublicationStage) -> PublicationCandidate:
    """REQUEST_STAGE_ADVANCE — sequencing only; does not invent policy facts."""
    cur = _STAGE_ORDER.index(candidate.stage)
    tgt = _STAGE_ORDER.index(to_stage)
    if tgt != cur + 1:
        raise PublicationPipelineError(f"ILLEGAL_PUBLICATION_JUMP:{candidate.stage.value}->{to_stage.value}")
    if to_stage == PublicationStage.STRUCTURED_EXTRACTION and candidate.model_extracted:
        candidate.notes.append("MODEL_EXTRACTED_CANDIDATE_NE_GOVERNED_KNOWLEDGE")
    if to_stage == PublicationStage.RUNTIME_ELIGIBILITY:
        if not (
            candidate.provenance_complete
            and candidate.evidence_linked
            and candidate.conflict_clear
            and candidate.safety_clear
            and candidate.governance_approved
        ):
            raise PublicationPipelineError("RUNTIME_ELIGIBILITY_WITHOUT_GOVERNANCE")
        # Clinical runtime eligibility is a separate policy derivation.
        candidate.runtime_eligible = False
        candidate.notes.append("RUNTIME_STAGE_REACHED_CLINICAL_ELIGIBILITY_SEPARATE")
    candidate.stage = to_stage
    return candidate


def assert_no_direct_runtime_publish(*, from_stage: PublicationStage, to_stage: PublicationStage) -> None:
    if from_stage == PublicationStage.RAW_SOURCE_RECORD and to_stage == PublicationStage.RUNTIME_ELIGIBILITY:
        raise PublicationPipelineError("SOURCE_DIRECT_RUNTIME_ANSWER_FORBIDDEN")


def trial_registry_forbids_clinical_runtime(artifact_type: Optional[str]) -> bool:
    return str(artifact_type or "").upper() in {"CLINICAL_TRIAL_RECORD", "CLINICAL_TRIAL"}


def derive_clinical_runtime_eligible(
    *,
    artifact_type: Optional[str],
    medical_safety_state: str,
    provenance_complete: bool,
    evidence_linked: bool,
    conflict_clear: bool,
    safety_clear: bool,
    governance_approved: bool,
    rights_allowed: bool,
) -> tuple[bool, str]:
    """Fail-closed clinical runtime eligibility (not stage position)."""
    if trial_registry_forbids_clinical_runtime(artifact_type):
        return False, "TRIAL_REGISTRATION_NE_PROVEN_TREATMENT"
    if str(medical_safety_state or "").upper() == MedicalSafetyState.UNKNOWN.value:
        return False, "UNKNOWN_SAFETY_NOT_CLINICAL_RUNTIME_ELIGIBLE"
    if not safety_clear:
        return False, "SAFETY_NOT_CLEAR"
    if not provenance_complete:
        return False, "PROVENANCE_INCOMPLETE"
    if not evidence_linked:
        return False, "EVIDENCE_NOT_LINKED"
    if not conflict_clear:
        return False, "CONFLICT_NOT_CLEAR"
    if not governance_approved:
        return False, "GOVERNANCE_NOT_APPROVED"
    if not rights_allowed:
        return False, "RIGHTS_NOT_ALLOWED"
    return True, "OK"


def verify_provenance_complete(db: Session, *, knowledge_unit_id: int) -> bool:
    prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=knowledge_unit_id).first()
    if prov is None:
        return False
    if getattr(prov, "source_profile_id", None) is None:
        return False
    if not str(getattr(prov, "retrieval_method", "") or "").strip():
        return False
    return True


def verify_evidence_linked(db: Session, *, knowledge_unit_id: int) -> bool:
    if not hasattr(models, "I5KnowledgeUnitEvidenceLink"):
        return False
    return (
        db.query(models.I5KnowledgeUnitEvidenceLink)
        .filter_by(knowledge_unit_id=knowledge_unit_id)
        .first()
        is not None
    )


def evaluate_conflict_clear(*, conflict_state: Optional[str], evaluated: bool) -> bool:
    """UNKNOWN/unevaluated → fail closed. Explicit NONE after evaluation → clear."""
    if not evaluated:
        return False
    return str(conflict_state or "").upper() == "NONE"


def evaluate_safety_clear(*, medical_safety_state: Optional[str]) -> bool:
    return str(medical_safety_state or "").upper() == MedicalSafetyState.CLEARED.value


def source_has_approved_governance(db: Session, *, source_profile_id: int) -> bool:
    """Reuse I5GovernanceDecision on SOURCE_PROFILE — no parallel governance SoT."""
    q = (
        db.query(models.I5GovernanceDecision)
        .filter_by(
            entity_type=GovernanceEntityType.SOURCE_PROFILE.value,
            entity_id=source_profile_id,
            outcome=GovernanceDecisionOutcome.APPROVED.value,
        )
        .filter(
            models.I5GovernanceDecision.decision_type.in_(
                [
                    GovernanceDecisionType.APPROVAL.value,
                    GovernanceDecisionType.ACTIVATION.value,
                    GovernanceDecisionType.AUTOMATION_REVIEW.value,
                ]
            )
        )
    )
    return q.first() is not None


def advance_through_normalization(candidate: PublicationCandidate) -> PublicationCandidate:
    """Fetch/normalize path — stops before claiming evidence/governance truth."""
    for stage in (
        PublicationStage.NORMALIZED_CANDIDATE,
        PublicationStage.STRUCTURED_EXTRACTION,
        PublicationStage.VALIDATION,
    ):
        candidate = advance_stage(candidate, stage)
    return candidate
