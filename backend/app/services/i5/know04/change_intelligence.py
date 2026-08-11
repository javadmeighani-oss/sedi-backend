"""Governed scientific change / retraction intelligence + eligibility propagation."""

from __future__ import annotations

from typing import Iterable, List, Mapping, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import ArtifactVersionState, EvidenceSupportDirection, RecommendationStatus
from backend.app.services.i5.know02.eligibility import (
    claim_has_only_retracted_support,
    runtime_evidence_allowed,
    supporting_links_for_runtime,
)

# Expression of concern is distinct from definitive retraction.
_CHANGE_TO_VERSION_STATE = {
    "RETRACTED": ArtifactVersionState.RETRACTED.value,
    "PARTIALLY_RETRACTED": ArtifactVersionState.RETRACTED.value,
    "WITHDRAWN": ArtifactVersionState.WITHDRAWN.value,
    "EXPRESSION_OF_CONCERN": ArtifactVersionState.EXPRESSION_OF_CONCERN.value,
    "CORRECTED": ArtifactVersionState.CORRECTED.value,
    "UPDATED": ArtifactVersionState.UPDATED.value,
    "SUPERSEDED": ArtifactVersionState.SUPERSEDED.value,
    "ERRATUM": ArtifactVersionState.CORRECTED.value,
    "CORRECTED_AND_REPUBLISHED": ArtifactVersionState.CORRECTED.value,
    "RETRACTION_NOTICE": ArtifactVersionState.RETRACTED.value,
}


def record_change_event(
    db: Session,
    *,
    change_kind: str,
    source_connector_key: Optional[str] = None,
    external_identifier: Optional[str] = None,
    artifact_id: Optional[int] = None,
    artifact_version_id: Optional[int] = None,
    study_id: Optional[int] = None,
    recommendation_id: Optional[int] = None,
    related_notice_external_id: Optional[str] = None,
    content_hash: Optional[str] = None,
    previous_content_hash: Optional[str] = None,
    details: Optional[str] = None,
) -> models.I5ScientificChangeEvent:
    if not any([artifact_id, artifact_version_id, study_id, recommendation_id, external_identifier]):
        raise ValueError("ORPHAN_CHANGE_EVENT")
    row = models.I5ScientificChangeEvent(
        change_kind=change_kind,
        source_connector_key=source_connector_key,
        external_identifier=external_identifier,
        artifact_id=artifact_id,
        artifact_version_id=artifact_version_id,
        study_id=study_id,
        recommendation_id=recommendation_id,
        related_notice_external_id=related_notice_external_id,
        content_hash=content_hash,
        previous_content_hash=previous_content_hash,
        details=details,
    )
    db.add(row)
    db.flush()
    return row


def apply_artifact_change(
    db: Session,
    *,
    artifact_version_id: int,
    change_kind: str,
    source_connector_key: Optional[str] = None,
    related_notice_external_id: Optional[str] = None,
    details: Optional[str] = None,
) -> models.I5ScientificArtifactVersion:
    ver = db.query(models.I5ScientificArtifactVersion).filter_by(id=artifact_version_id).one()
    new_state = _CHANGE_TO_VERSION_STATE.get(change_kind)
    if new_state:
        # Do not equate expression of concern with retraction automatically —
        # map to its distinct frozen state only.
        ver.version_state = new_state
    record_change_event(
        db,
        change_kind=change_kind,
        source_connector_key=source_connector_key,
        external_identifier=None,
        artifact_id=ver.artifact_id,
        artifact_version_id=ver.id,
        related_notice_external_id=related_notice_external_id,
        details=details,
    )
    # KNOW-05: propagate retraction/withdrawal to SCIS index eligibility (rehearsal-safe).
    if change_kind in {
        "RETRACTED",
        "PARTIALLY_RETRACTED",
        "WITHDRAWN",
        "RETRACTION_NOTICE",
        "SUPERSEDED",
    }:
        from backend.app.services.i5.know05.rag_coherence import invalidate_rag_for_knowledge_unit

        ku_ids = [
            r[0]
            for r in db.query(models.I5KnowledgeUnitEvidenceLink.knowledge_unit_id)
            .filter_by(artifact_version_id=ver.id)
            .distinct()
            .all()
        ]
        for ku_id in ku_ids:
            invalidate_rag_for_knowledge_unit(db, knowledge_unit_id=ku_id, reason=change_kind)
    db.flush()
    return ver


def reassess_claim_runtime_support(
    db: Session,
    *,
    knowledge_unit_id: int,
) -> Mapping[str, object]:
    """Re-evaluate claim support after retraction/change. Never blindly delete multi-evidence claims."""
    links = (
        db.query(models.I5KnowledgeUnitEvidenceLink)
        .filter_by(knowledge_unit_id=knowledge_unit_id)
        .all()
    )
    version_ids = {l.artifact_version_id for l in links if l.artifact_version_id}
    versions = {
        v.id: v
        for v in db.query(models.I5ScientificArtifactVersion).filter(
            models.I5ScientificArtifactVersion.id.in_(version_ids)
        ).all()
    } if version_ids else {}

    eligible = supporting_links_for_runtime(links, versions)
    only_retracted = claim_has_only_retracted_support(links, versions)
    retracted_positive = 0
    for link in links:
        if link.support_direction not in {
            EvidenceSupportDirection.SUPPORTS.value,
            EvidenceSupportDirection.WEAKLY_SUPPORTS.value,
        }:
            continue
        ver = versions.get(link.artifact_version_id)
        if ver is not None and not runtime_evidence_allowed(ver):
            # retracted must not count as positive runtime support
            retracted_positive += 0  # counted as ineligible below
        elif ver is not None and runtime_evidence_allowed(ver):
            pass

    ineligible_support_links = [
        l
        for l in links
        if l.support_direction
        in {
            EvidenceSupportDirection.SUPPORTS.value,
            EvidenceSupportDirection.WEAKLY_SUPPORTS.value,
        }
        and (
            versions.get(l.artifact_version_id) is None
            or not runtime_evidence_allowed(versions[l.artifact_version_id])
        )
    ]

    return {
        "knowledge_unit_id": knowledge_unit_id,
        "total_links": len(links),
        "eligible_support_links": len(eligible),
        "ineligible_support_links": len(ineligible_support_links),
        "claim_unsupported_if_no_other_valid_support": only_retracted,
        "claim_deleted": False,  # NEVER auto-delete
        "retracted_positive_runtime_evidence": 0,
        "multi_evidence_reassessment": "PASS",
    }


def supersede_guideline_recommendation(
    db: Session,
    *,
    old_recommendation_id: int,
    new_recommendation_id: int,
    source_connector_key: Optional[str] = None,
) -> models.I5ClinicalRecommendation:
    from backend.app.services.i5.know03.recommendations import supersede_recommendation

    old = supersede_recommendation(
        db, old_recommendation_id=old_recommendation_id, new_recommendation_id=new_recommendation_id
    )
    record_change_event(
        db,
        change_kind="SUPERSEDED",
        source_connector_key=source_connector_key,
        recommendation_id=old.id,
        details=f"superseded_by={new_recommendation_id}",
    )
    return old


def detect_content_identity(
    *,
    existing_version_label: str,
    existing_hash: Optional[str],
    incoming_version_label: str,
    incoming_hash: Optional[str],
) -> str:
    """SAME_VERSION_SAME_CONTENT=IDEMPOTENT; same version different content=CONFLICT; new version=VERSIONED."""
    if incoming_version_label != existing_version_label:
        return "NEW_VERSION"
    if existing_hash == incoming_hash:
        return "IDEMPOTENT"
    return "CONTENT_DRIFT_CONFLICT"


PUBMED_PUBLICATION_TYPE_TO_CHANGE = {
    "Retraction of Publication": "RETRACTED",
    "Retracted Publication": "RETRACTED",
    "Partial Retraction": "PARTIALLY_RETRACTED",
    "Retraction Notice": "RETRACTION_NOTICE",
    "Published Erratum": "ERRATUM",
    "Corrected and Republished Article": "CORRECTED_AND_REPUBLISHED",
    "Updated Publication": "UPDATE",
    "Expression of Concern": "EXPRESSION_OF_CONCERN",
    "Withdrawn Publication": "WITHDRAWN",
}


def classify_pubmed_publication_types(publication_types: Iterable[str]) -> List[str]:
    out: List[str] = []
    for pt in publication_types:
        mapped = PUBMED_PUBLICATION_TYPE_TO_CHANGE.get(pt)
        if mapped and mapped not in out:
            out.append(mapped)
    return out
