"""Clinical study / population / intervention / outcome services."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    ComparatorKind,
    InterventionCategory,
    OutcomeCategory,
    OutcomeDirectionOfBenefit,
    PopulationCriterionType,
    RiskOfBiasLabel,
    StudyArtifactRole,
    StudyConditionRole,
    StudyDesign,
    StudyInterventionRole,
    StudyOutcomeRole,
    TerminologySystem,
)


def upsert_clinical_study(
    db: Session,
    *,
    study_key: str,
    study_design: str,
    primary_artifact_id: Optional[int] = None,
    primary_artifact_version_id: Optional[int] = None,
    registry_identifier: Optional[str] = None,
    title: Optional[str] = None,
    sample_size: Optional[int] = None,
    study_status: str = "UNKNOWN",
    randomized: Optional[bool] = None,
    controlled: Optional[bool] = None,
    blinded: Optional[bool] = None,
    risk_of_bias: Optional[str] = None,
    evidence_quality: Optional[str] = None,
    **extra,
) -> models.I5ClinicalStudy:
    StudyDesign(study_design)
    if risk_of_bias:
        RiskOfBiasLabel(risk_of_bias)
    if sample_size is not None and sample_size < 0:
        raise ValueError("NEGATIVE_SAMPLE_SIZE")
    if registry_identifier:
        other = (
            db.query(models.I5ClinicalStudy)
            .filter(
                models.I5ClinicalStudy.registry_identifier == registry_identifier,
                models.I5ClinicalStudy.study_key != study_key,
            )
            .first()
        )
        if other:
            raise ValueError("STUDY_REGISTRY_IDENTITY_CONFLICT")
    row = db.query(models.I5ClinicalStudy).filter_by(study_key=study_key).first()
    if row is None:
        row = models.I5ClinicalStudy(study_key=study_key, study_design=study_design)
        db.add(row)
    row.study_design = study_design
    row.primary_artifact_id = primary_artifact_id
    row.primary_artifact_version_id = primary_artifact_version_id
    row.registry_identifier = registry_identifier
    row.title = title
    row.sample_size = sample_size
    row.study_status = study_status
    row.randomized = randomized
    row.controlled = controlled
    row.blinded = blinded
    row.risk_of_bias = risk_of_bias
    row.evidence_quality = evidence_quality
    for k, v in extra.items():
        if hasattr(row, k):
            setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def link_study_artifact(
    db: Session, *, study_id: int, artifact_version_id: int, artifact_role: str
) -> models.I5StudyArtifactLink:
    StudyArtifactRole(artifact_role)
    existing = (
        db.query(models.I5StudyArtifactLink)
        .filter_by(study_id=study_id, artifact_version_id=artifact_version_id, artifact_role=artifact_role)
        .first()
    )
    if existing:
        return existing
    row = models.I5StudyArtifactLink(
        study_id=study_id, artifact_version_id=artifact_version_id, artifact_role=artifact_role
    )
    db.add(row)
    db.flush()
    return row


def link_study_condition(
    db: Session, *, study_id: int, concept_id: int, condition_role: str = StudyConditionRole.PRIMARY_CONDITION.value
) -> models.I5StudyConditionLink:
    StudyConditionRole(condition_role)
    existing = (
        db.query(models.I5StudyConditionLink)
        .filter_by(study_id=study_id, concept_id=concept_id, condition_role=condition_role)
        .first()
    )
    if existing:
        return existing
    row = models.I5StudyConditionLink(study_id=study_id, concept_id=concept_id, condition_role=condition_role)
    db.add(row)
    db.flush()
    return row


def upsert_population(
    db: Session, *, study_id: int, population_key: str, **fields
) -> models.I5StudyPopulation:
    row = (
        db.query(models.I5StudyPopulation)
        .filter_by(study_id=study_id, population_key=population_key)
        .first()
    )
    if row is None:
        row = models.I5StudyPopulation(study_id=study_id, population_key=population_key)
        db.add(row)
    for k, v in fields.items():
        if hasattr(row, k):
            setattr(row, k, v)
    if row.sample_size is not None and row.sample_size < 0:
        raise ValueError("NEGATIVE_SAMPLE_SIZE")
    db.flush()
    return row


def add_population_criterion(
    db: Session,
    *,
    population_id: int,
    criterion_type: str,
    operator: Optional[str] = None,
    value_text: Optional[str] = None,
    value_numeric: Optional[float] = None,
    unit: Optional[str] = None,
    concept_id: Optional[int] = None,
    is_exclusion: bool = False,
    required: bool = True,
    provenance_note: Optional[str] = None,
) -> models.I5StudyPopulationCriterion:
    PopulationCriterionType(criterion_type)
    row = models.I5StudyPopulationCriterion(
        population_id=population_id,
        criterion_type=criterion_type,
        operator=operator,
        value_text=value_text,
        value_numeric=value_numeric,
        unit=unit,
        concept_id=concept_id,
        is_exclusion=is_exclusion,
        required=required,
        provenance_note=provenance_note,
    )
    db.add(row)
    db.flush()
    return row


def upsert_intervention(
    db: Session,
    *,
    intervention_key: str,
    preferred_name: str,
    intervention_category: str,
    concept_id: Optional[int] = None,
    description: Optional[str] = None,
) -> models.I5Intervention:
    InterventionCategory(intervention_category)
    row = db.query(models.I5Intervention).filter_by(intervention_key=intervention_key).first()
    if row is None:
        row = models.I5Intervention(
            intervention_key=intervention_key,
            preferred_name=preferred_name,
            intervention_category=intervention_category,
        )
        db.add(row)
    row.preferred_name = preferred_name
    row.intervention_category = intervention_category
    row.concept_id = concept_id
    row.description = description
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def map_intervention(
    db: Session,
    *,
    intervention_id: int,
    terminology_system: str,
    external_code: str,
    release_version: Optional[str] = None,
    provenance_note: Optional[str] = None,
) -> models.I5InterventionMapping:
    TerminologySystem(terminology_system)
    existing = (
        db.query(models.I5InterventionMapping)
        .filter_by(
            terminology_system=terminology_system,
            external_code=external_code,
            release_version=release_version,
        )
        .first()
    )
    if existing:
        if existing.intervention_id == intervention_id:
            if provenance_note is not None:
                existing.provenance_note = provenance_note
            db.flush()
            return existing
        from backend.app.services.i5.know04.terminology_remap import record_mapping_conflict

        raise record_mapping_conflict(
            db,
            mapping_kind="INTERVENTION",
            terminology_system=terminology_system,
            external_code=external_code,
            release_version=release_version,
            existing_target_id=existing.intervention_id,
            incoming_target_id=intervention_id,
            existing_mapping_id=existing.id,
        )
    row = models.I5InterventionMapping(
        intervention_id=intervention_id,
        terminology_system=terminology_system,
        external_code=external_code,
        release_version=release_version,
        provenance_note=provenance_note,
    )
    db.add(row)
    db.flush()
    return row


def link_study_intervention(
    db: Session,
    *,
    study_id: int,
    intervention_id: int,
    intervention_role: str,
    comparator_kind: Optional[str] = None,
    **fields,
) -> models.I5StudyIntervention:
    StudyInterventionRole(intervention_role)
    if comparator_kind:
        ComparatorKind(comparator_kind)
    existing = (
        db.query(models.I5StudyIntervention)
        .filter_by(study_id=study_id, intervention_id=intervention_id, intervention_role=intervention_role)
        .first()
    )
    if existing:
        return existing
    row = models.I5StudyIntervention(
        study_id=study_id,
        intervention_id=intervention_id,
        intervention_role=intervention_role,
        comparator_kind=comparator_kind,
    )
    for k, v in fields.items():
        if hasattr(row, k):
            setattr(row, k, v)
    db.add(row)
    db.flush()
    return row


def upsert_outcome(
    db: Session,
    *,
    outcome_key: str,
    preferred_name: str,
    outcome_category: str,
    direction_of_benefit: Optional[str] = None,
    measurement_scale: Optional[str] = None,
    unit: Optional[str] = None,
    concept_id: Optional[int] = None,
) -> models.I5ClinicalOutcome:
    OutcomeCategory(outcome_category)
    if direction_of_benefit:
        OutcomeDirectionOfBenefit(direction_of_benefit)
    row = db.query(models.I5ClinicalOutcome).filter_by(outcome_key=outcome_key).first()
    if row is None:
        row = models.I5ClinicalOutcome(
            outcome_key=outcome_key,
            preferred_name=preferred_name,
            outcome_category=outcome_category,
        )
        db.add(row)
    row.preferred_name = preferred_name
    row.outcome_category = outcome_category
    row.direction_of_benefit = direction_of_benefit
    row.measurement_scale = measurement_scale
    row.unit = unit
    row.concept_id = concept_id
    db.flush()
    return row


def link_study_outcome(
    db: Session,
    *,
    study_id: int,
    outcome_id: int,
    outcome_role: str = StudyOutcomeRole.PRIMARY.value,
    time_point: Optional[str] = None,
    is_harm: bool = False,
    clinically_important_threshold: Optional[str] = None,
) -> models.I5StudyOutcome:
    StudyOutcomeRole(outcome_role)
    existing = (
        db.query(models.I5StudyOutcome)
        .filter_by(study_id=study_id, outcome_id=outcome_id, outcome_role=outcome_role)
        .first()
    )
    if existing:
        return existing
    row = models.I5StudyOutcome(
        study_id=study_id,
        outcome_id=outcome_id,
        outcome_role=outcome_role,
        time_point=time_point,
        is_harm=is_harm,
        clinically_important_threshold=clinically_important_threshold,
    )
    db.add(row)
    db.flush()
    return row
