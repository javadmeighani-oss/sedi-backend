"""Runtime eligibility helpers for KNOW-02 evidence links (no full publication engine)."""

from __future__ import annotations

from typing import Iterable, List

from backend.app import models
from backend.app.services.i5.enums import ArtifactVersionState, EvidenceSupportDirection

_BLOCKING_VERSION_STATES = {
    ArtifactVersionState.RETRACTED.value,
    ArtifactVersionState.WITHDRAWN.value,
}


def runtime_evidence_allowed(version: models.I5ScientificArtifactVersion) -> bool:
    """Retracted/withdrawn versions cannot silently support accepted runtime claims."""
    return version.version_state not in _BLOCKING_VERSION_STATES


def supporting_links_for_runtime(
    links: Iterable[models.I5KnowledgeUnitEvidenceLink],
    versions_by_id: dict,
) -> List[models.I5KnowledgeUnitEvidenceLink]:
    """Filter SUPPORTS/WEAKLY_SUPPORTS links whose artifact version is still eligible."""
    out: List[models.I5KnowledgeUnitEvidenceLink] = []
    for link in links:
        if link.support_direction not in {
            EvidenceSupportDirection.SUPPORTS.value,
            EvidenceSupportDirection.WEAKLY_SUPPORTS.value,
        }:
            continue
        ver = versions_by_id.get(link.artifact_version_id)
        if ver is None or not runtime_evidence_allowed(ver):
            continue
        out.append(link)
    return out


def claim_has_only_retracted_support(
    links: Iterable[models.I5KnowledgeUnitEvidenceLink],
    versions_by_id: dict,
) -> bool:
    supportish = [
        l
        for l in links
        if l.support_direction
        in {
            EvidenceSupportDirection.SUPPORTS.value,
            EvidenceSupportDirection.WEAKLY_SUPPORTS.value,
        }
    ]
    if not supportish:
        return False
    eligible = supporting_links_for_runtime(supportish, versions_by_id)
    return len(eligible) == 0
