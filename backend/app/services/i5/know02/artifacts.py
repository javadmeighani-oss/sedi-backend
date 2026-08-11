"""Scientific artifact + multi-evidence + claim services (KNOW-02 + W0 integrity)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import ArtifactType, ArtifactVersionState, ClaimClass, EvidenceSupportDirection
from backend.app.services.i5.know02.eligibility import runtime_evidence_allowed


class ContentDriftConflict(ValueError):
    """Same artifact + version label + different content hash — never silent overwrite."""

    def __init__(
        self,
        *,
        artifact_id: int,
        version_label: str,
        existing_version_id: int,
        existing_content_hash: Optional[str],
        incoming_content_hash: Optional[str],
    ):
        self.artifact_id = artifact_id
        self.version_label = version_label
        self.existing_version_id = existing_version_id
        self.existing_content_hash = existing_content_hash
        self.incoming_content_hash = incoming_content_hash
        super().__init__(
            "CONTENT_DRIFT_CONFLICT:"
            f" artifact={artifact_id} label={version_label}"
            f" existing={existing_content_hash} incoming={incoming_content_hash}"
        )


def upsert_artifact(
    db: Session,
    *,
    artifact_key: str,
    artifact_type: str,
    title: Optional[str] = None,
    source_profile_id: Optional[int] = None,
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    nct_id: Optional[str] = None,
    pmcid: Optional[str] = None,
    isbn: Optional[str] = None,
    guideline_id: Optional[str] = None,
    publisher_family: Optional[str] = None,
    canonical_url: Optional[str] = None,
) -> models.I5ScientificArtifact:
    ArtifactType(artifact_type)
    row = db.query(models.I5ScientificArtifact).filter_by(artifact_key=artifact_key).first()
    if row is None:
        row = models.I5ScientificArtifact(artifact_key=artifact_key, artifact_type=artifact_type)
        db.add(row)
    row.artifact_type = artifact_type
    row.title = title
    row.source_profile_id = source_profile_id
    row.doi = doi
    row.pmid = pmid
    row.nct_id = nct_id
    row.pmcid = pmcid
    row.isbn = isbn
    row.guideline_id = guideline_id
    row.publisher_family = publisher_family
    row.canonical_url = canonical_url
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def _record_content_drift(
    db: Session,
    *,
    existing: models.I5ScientificArtifactVersion,
    incoming_content_hash: Optional[str],
    locator: Optional[str],
) -> None:
    art = db.query(models.I5ScientificArtifact).filter_by(id=existing.artifact_id).one()
    db.add(
        models.I5ArtifactVersionContentDriftEvent(
            artifact_id=existing.artifact_id,
            version_label=existing.version_label,
            existing_version_id=existing.id,
            existing_content_hash=existing.content_hash,
            incoming_content_hash=incoming_content_hash,
            source_profile_id=art.source_profile_id,
            locator=locator or existing.locator,
            publisher_family=art.publisher_family,
            retrieval_note="CONTENT_DRIFT_CONFLICT detected; historical version not mutated",
        )
    )
    db.flush()


def add_artifact_version(
    db: Session,
    *,
    artifact_id: int,
    version_label: str,
    version_state: str = ArtifactVersionState.PUBLISHED.value,
    content_hash: Optional[str] = None,
    title_at_version: Optional[str] = None,
    abstract_or_summary: Optional[str] = None,
    supersedes_version_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
    locator: Optional[str] = None,
) -> models.I5ScientificArtifactVersion:
    ArtifactVersionState(version_state)
    if supersedes_version_id is not None:
        if supersedes_version_id == 0:
            raise ValueError("ORPHAN_SUPERSESSION")
        parent = (
            db.query(models.I5ScientificArtifactVersion)
            .filter_by(id=supersedes_version_id)
            .first()
        )
        if parent is None:
            raise ValueError("ORPHAN_SUPERSESSION")
        if parent.artifact_id != artifact_id:
            raise ValueError("CROSS_ARTIFACT_SUPERSESSION_FORBIDDEN")

    existing = (
        db.query(models.I5ScientificArtifactVersion)
        .filter_by(artifact_id=artifact_id, version_label=version_label)
        .first()
    )
    if existing:
        # IDEMPOTENT: same label + same hash (including both None)
        if existing.content_hash == content_hash:
            return existing
        # NF5: same label + different hash → conflict; never silent overwrite
        _record_content_drift(
            db, existing=existing, incoming_content_hash=content_hash, locator=locator
        )
        raise ContentDriftConflict(
            artifact_id=artifact_id,
            version_label=version_label,
            existing_version_id=existing.id,
            existing_content_hash=existing.content_hash,
            incoming_content_hash=content_hash,
        )

    row = models.I5ScientificArtifactVersion(
        artifact_id=artifact_id,
        version_label=version_label,
        version_state=version_state,
        content_hash=content_hash,
        title_at_version=title_at_version,
        abstract_or_summary=abstract_or_summary,
        supersedes_version_id=supersedes_version_id,
        raw_evidence_id=raw_evidence_id,
        locator=locator,
        published_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    if supersedes_version_id is not None and supersedes_version_id == row.id:
        raise ValueError("SELF_SUPERSESSION_BLOCKED")
    return row


def mark_version_state(
    db: Session, *, version_id: int, version_state: str
) -> models.I5ScientificArtifactVersion:
    """Lifecycle transition only (state field); historical row retained."""
    ArtifactVersionState(version_state)
    row = db.query(models.I5ScientificArtifactVersion).filter_by(id=version_id).one()
    row.version_state = version_state
    db.flush()
    return row


def link_evidence(
    db: Session,
    *,
    knowledge_unit_id: int,
    artifact_version_id: int,
    support_direction: str,
    evidence_role: Optional[str] = None,
    locator: Optional[str] = None,
    study_id: Optional[int] = None,
    enforce_runtime_support: bool = False,
) -> models.I5KnowledgeUnitEvidenceLink:
    EvidenceSupportDirection(support_direction)
    if enforce_runtime_support and support_direction in {
        EvidenceSupportDirection.SUPPORTS.value,
        EvidenceSupportDirection.WEAKLY_SUPPORTS.value,
    }:
        ver = db.query(models.I5ScientificArtifactVersion).filter_by(id=artifact_version_id).one()
        if not runtime_evidence_allowed(ver):
            raise PermissionError("RETRACTED_ONLY_EVIDENCE_CANNOT_SUPPORT_RUNTIME_CLAIM")
    existing = (
        db.query(models.I5KnowledgeUnitEvidenceLink)
        .filter_by(
            knowledge_unit_id=knowledge_unit_id,
            artifact_version_id=artifact_version_id,
            support_direction=support_direction,
        )
        .first()
    )
    if existing:
        if study_id is not None and existing.study_id is None:
            existing.study_id = study_id
            db.flush()
        return existing
    row = models.I5KnowledgeUnitEvidenceLink(
        knowledge_unit_id=knowledge_unit_id,
        artifact_version_id=artifact_version_id,
        support_direction=support_direction,
        evidence_role=evidence_role,
        locator=locator,
        study_id=study_id,
        retrieved_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def upsert_claim_detail(
    db: Session,
    *,
    knowledge_unit_id: int,
    claim_class: str,
    subject_concept_id: Optional[int] = None,
    predicate: Optional[str] = None,
    object_concept_id: Optional[int] = None,
    population_context: Optional[str] = None,
    intervention_text: Optional[str] = None,
    comparator_text: Optional[str] = None,
    outcome_text: Optional[str] = None,
    effect_direction: Optional[str] = None,
    recommendation_status: Optional[str] = None,
    experimental_status: Optional[str] = None,
    certainty_note: Optional[str] = None,
) -> models.I5KnowledgeClaimDetail:
    ClaimClass(claim_class)
    row = db.query(models.I5KnowledgeClaimDetail).filter_by(knowledge_unit_id=knowledge_unit_id).first()
    if row is None:
        row = models.I5KnowledgeClaimDetail(knowledge_unit_id=knowledge_unit_id, claim_class=claim_class)
        db.add(row)
    row.claim_class = claim_class
    row.subject_concept_id = subject_concept_id
    row.predicate = predicate
    row.object_concept_id = object_concept_id
    row.population_context = population_context
    row.intervention_text = intervention_text
    row.comparator_text = comparator_text
    row.outcome_text = outcome_text
    row.effect_direction = effect_direction
    row.recommendation_status = recommendation_status
    row.experimental_status = experimental_status
    row.certainty_note = certainty_note
    row.updated_at = datetime.utcnow()
    db.flush()
    return row
