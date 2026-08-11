"""Governed publication pipeline — never SOURCE → direct runtime answer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


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
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "external_identifier": self.external_identifier,
            "source_connector_key": self.source_connector_key,
            "stage": self.stage.value,
            "model_extracted": self.model_extracted,
            "runtime_eligible": self.runtime_eligible,
            "notes": list(self.notes),
        }


def advance_stage(candidate: PublicationCandidate, to_stage: PublicationStage) -> PublicationCandidate:
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
        candidate.runtime_eligible = True
    candidate.stage = to_stage
    return candidate


def assert_no_direct_runtime_publish(*, from_stage: PublicationStage, to_stage: PublicationStage) -> None:
    if from_stage == PublicationStage.RAW_SOURCE_RECORD and to_stage == PublicationStage.RUNTIME_ELIGIBILITY:
        raise PublicationPipelineError("SOURCE_DIRECT_RUNTIME_ANSWER_FORBIDDEN")
