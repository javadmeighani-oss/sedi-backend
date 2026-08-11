"""Clinical recommendations — separated from study results (paper ≠ recommendation)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    EvidenceSupportDirection,
    RecommendationDirection,
    RecommendationEvidenceTargetKind,
    RecommendationStatus,
)


def upsert_recommendation(
    db: Session,
    *,
    recommendation_key: str,
    source_artifact_version_id: int,
    recommended_action: str,
    recommendation_direction: str,
    knowledge_unit_id: Optional[int] = None,
    grading_system: Optional[str] = None,
    original_grade: Optional[str] = None,
    normalized_strength: Optional[str] = None,
    certainty_system: Optional[str] = None,
    original_certainty: Optional[str] = None,
    benefit_summary: Optional[str] = None,
    harm_summary: Optional[str] = None,
    exceptions: Optional[str] = None,
    contraindications: Optional[str] = None,
    monitoring_requirements: Optional[str] = None,
    target_population_text: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    effective_from: Optional[date] = None,
    effective_until: Optional[date] = None,
    status: str = RecommendationStatus.CURRENT.value,
) -> models.I5ClinicalRecommendation:
    RecommendationDirection(recommendation_direction)
    RecommendationStatus(status)
    if not db.query(models.I5ScientificArtifactVersion).filter_by(id=source_artifact_version_id).first():
        raise ValueError("ORPHAN_RECOMMENDATION_SOURCE")
    row = db.query(models.I5ClinicalRecommendation).filter_by(recommendation_key=recommendation_key).first()
    if row is None:
        row = models.I5ClinicalRecommendation(
            recommendation_key=recommendation_key,
            source_artifact_version_id=source_artifact_version_id,
            recommended_action=recommended_action,
            recommendation_direction=recommendation_direction,
        )
        db.add(row)
    row.source_artifact_version_id = source_artifact_version_id
    row.recommended_action = recommended_action
    row.recommendation_direction = recommendation_direction
    row.knowledge_unit_id = knowledge_unit_id
    row.grading_system = grading_system
    row.original_grade = original_grade
    row.normalized_strength = normalized_strength
    row.certainty_system = certainty_system
    row.original_certainty = original_certainty
    row.benefit_summary = benefit_summary
    row.harm_summary = harm_summary
    row.exceptions = exceptions
    row.contraindications = contraindications
    row.monitoring_requirements = monitoring_requirements
    row.target_population_text = target_population_text
    row.jurisdiction = jurisdiction
    row.effective_from = effective_from
    row.effective_until = effective_until
    row.status = status
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def link_recommendation_condition(
    db: Session, *, recommendation_id: int, concept_id: int, relation_role: str = "TARGET_CONDITION"
) -> models.I5ClinicalRecommendationConditionLink:
    existing = (
        db.query(models.I5ClinicalRecommendationConditionLink)
        .filter_by(recommendation_id=recommendation_id, concept_id=concept_id, relation_role=relation_role)
        .first()
    )
    if existing:
        return existing
    row = models.I5ClinicalRecommendationConditionLink(
        recommendation_id=recommendation_id, concept_id=concept_id, relation_role=relation_role
    )
    db.add(row)
    db.flush()
    return row


def _enforce_recommendation_evidence_target_xor(
    *,
    target_kind: str,
    knowledge_unit_id: Optional[int],
    artifact_version_id: Optional[int],
    study_id: Optional[int],
) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Exactly one evidence target column may be populated, matching target_kind."""
    populated = sum(x is not None for x in (knowledge_unit_id, artifact_version_id, study_id))
    if populated != 1:
        raise ValueError("MULTI_TARGET_RECOMMENDATION_EVIDENCE")
    if target_kind == RecommendationEvidenceTargetKind.KNOWLEDGE_UNIT.value:
        if knowledge_unit_id is None or artifact_version_id is not None or study_id is not None:
            raise ValueError("TARGET_KIND_MISMATCH")
        return knowledge_unit_id, None, None
    if target_kind in {
        RecommendationEvidenceTargetKind.ARTIFACT_VERSION.value,
        RecommendationEvidenceTargetKind.SYSTEMATIC_REVIEW_ARTIFACT.value,
    }:
        if artifact_version_id is None or knowledge_unit_id is not None or study_id is not None:
            raise ValueError("TARGET_KIND_MISMATCH")
        return None, artifact_version_id, None
    if target_kind == RecommendationEvidenceTargetKind.CLINICAL_STUDY.value:
        if study_id is None or knowledge_unit_id is not None or artifact_version_id is not None:
            raise ValueError("TARGET_KIND_MISMATCH")
        return None, None, study_id
    raise ValueError("ORPHAN_RECOMMENDATION_EVIDENCE")


def link_recommendation_evidence(
    db: Session,
    *,
    recommendation_id: int,
    target_kind: str,
    knowledge_unit_id: Optional[int] = None,
    artifact_version_id: Optional[int] = None,
    study_id: Optional[int] = None,
    support_direction: str = EvidenceSupportDirection.SUPPORTS.value,
    notes: Optional[str] = None,
) -> models.I5ClinicalRecommendationEvidenceLink:
    RecommendationEvidenceTargetKind(target_kind)
    EvidenceSupportDirection(support_direction)
    knowledge_unit_id, artifact_version_id, study_id = _enforce_recommendation_evidence_target_xor(
        target_kind=target_kind,
        knowledge_unit_id=knowledge_unit_id,
        artifact_version_id=artifact_version_id,
        study_id=study_id,
    )
    row = models.I5ClinicalRecommendationEvidenceLink(
        recommendation_id=recommendation_id,
        target_kind=target_kind,
        knowledge_unit_id=knowledge_unit_id,
        artifact_version_id=artifact_version_id,
        study_id=study_id,
        support_direction=support_direction,
        notes=notes,
    )
    db.add(row)
    db.flush()
    return row


def supersede_recommendation(
    db: Session, *, old_recommendation_id: int, new_recommendation_id: int
) -> models.I5ClinicalRecommendation:
    if old_recommendation_id == new_recommendation_id:
        raise ValueError("SELF_SUPERSESSION_BLOCKED")
    old = db.query(models.I5ClinicalRecommendation).filter_by(id=old_recommendation_id).one()
    new = db.query(models.I5ClinicalRecommendation).filter_by(id=new_recommendation_id).one()
    old.superseded_by_id = new.id
    old.status = RecommendationStatus.SUPERSEDED.value
    new.status = RecommendationStatus.CURRENT.value
    db.flush()
    return old
