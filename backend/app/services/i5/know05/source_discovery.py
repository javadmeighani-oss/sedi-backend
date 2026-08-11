"""Candidate source discovery lifecycle — discovered ≠ trusted clinical authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CandidateSourceStage(str, Enum):
    DISCOVERED = "DISCOVERED"
    AUTHORITY_VERIFIED = "AUTHORITY_VERIFIED"
    ROLE_CLASSIFIED = "ROLE_CLASSIFIED"
    RIGHTS_REVIEWED = "RIGHTS_REVIEWED"
    GOVERNANCE_APPROVED = "GOVERNANCE_APPROVED"
    CONNECTOR_ELIGIBLE = "CONNECTOR_ELIGIBLE"


_ORDER = list(CandidateSourceStage)


class CandidateSourceError(ValueError):
    pass


@dataclass
class CandidateSource:
    locator: str
    stage: CandidateSourceStage = CandidateSourceStage.DISCOVERED
    trusted_source: bool = False
    clinical_authority: bool = False
    iran_directory_boundary: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "locator": self.locator,
            "stage": self.stage.value,
            "trusted_source": self.trusted_source,
            "clinical_authority": self.clinical_authority,
            "iran_directory_boundary": self.iran_directory_boundary,
            "notes": list(self.notes),
        }


def advance_candidate(c: CandidateSource, to_stage: CandidateSourceStage) -> CandidateSource:
    if _ORDER.index(to_stage) != _ORDER.index(c.stage) + 1:
        raise CandidateSourceError(f"ILLEGAL_CANDIDATE_JUMP:{c.stage.value}->{to_stage.value}")
    if to_stage == CandidateSourceStage.CONNECTOR_ELIGIBLE and not c.trusted_source:
        # Still not automatic clinical authority
        c.clinical_authority = False
        c.notes.append("CANDIDATE_NE_TRUSTED_SOURCE")
    c.stage = to_stage
    return c


def assert_discovered_not_authority(c: CandidateSource) -> None:
    if c.stage == CandidateSourceStage.DISCOVERED and c.clinical_authority:
        raise CandidateSourceError("DISCOVERED_WEB_PAGE_AS_CLINICAL_AUTHORITY")
