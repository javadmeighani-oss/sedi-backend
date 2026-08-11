"""Effect estimate persistence with numeric integrity (no clinical inference)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    ClinicalSignificanceLabel,
    EffectMeasure,
    StatisticalSignificanceLabel,
)
from backend.app.services.i5.know03.validation import validate_effect_payload


def add_effect_estimate(
    db: Session,
    *,
    study_id: int,
    study_outcome_id: int,
    effect_measure: str,
    population_id: Optional[int] = None,
    study_intervention_id: Optional[int] = None,
    study_comparator_id: Optional[int] = None,
    analysis_population: Optional[str] = None,
    effect_value: Optional[float] = None,
    ci_lower: Optional[float] = None,
    ci_upper: Optional[float] = None,
    confidence_level: Optional[float] = None,
    p_value: Optional[float] = None,
    absolute_effect: Optional[float] = None,
    relative_effect: Optional[float] = None,
    baseline_risk: Optional[float] = None,
    follow_up_duration: Optional[float] = None,
    follow_up_unit: Optional[str] = None,
    sample_size_analyzed: Optional[int] = None,
    event_count_intervention: Optional[int] = None,
    event_count_comparator: Optional[int] = None,
    statistical_significance: Optional[str] = None,
    clinical_significance: Optional[str] = None,
    notes: Optional[str] = None,
) -> models.I5StudyEffectEstimate:
    EffectMeasure(effect_measure)
    if statistical_significance:
        StatisticalSignificanceLabel(statistical_significance)
    if clinical_significance:
        ClinicalSignificanceLabel(clinical_significance)
    cleaned = validate_effect_payload(
        effect_value=effect_value,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        confidence_level=confidence_level,
        p_value=p_value,
        sample_size_analyzed=sample_size_analyzed,
        event_count_intervention=event_count_intervention,
        event_count_comparator=event_count_comparator,
    )
    row = models.I5StudyEffectEstimate(
        study_id=study_id,
        population_id=population_id,
        study_intervention_id=study_intervention_id,
        study_comparator_id=study_comparator_id,
        study_outcome_id=study_outcome_id,
        analysis_population=analysis_population,
        effect_measure=effect_measure,
        absolute_effect=absolute_effect,
        relative_effect=relative_effect,
        baseline_risk=baseline_risk,
        follow_up_duration=follow_up_duration,
        follow_up_unit=follow_up_unit,
        statistical_significance=statistical_significance,
        clinical_significance=clinical_significance,
        notes=notes,
        **cleaned,
    )
    db.add(row)
    db.flush()
    return row
