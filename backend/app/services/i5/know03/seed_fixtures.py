"""KNOW-03 synthetic fixtures — P0 + non-P0 + lifestyle; no real treatment claims."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    ComparatorKind,
    EffectMeasure,
    EvidenceSupportDirection,
    InterventionCategory,
    KnowledgeDimensionCode,
    OutcomeCategory,
    OutcomeDirectionOfBenefit,
    PopulationCriterionType,
    RecommendationDirection,
    RecommendationEvidenceTargetKind,
    RecommendationStatus,
    StudyArtifactRole,
    StudyConditionRole,
    StudyDesign,
    StudyInterventionRole,
    StudyOutcomeRole,
    TerminologySystem,
)
from backend.app.services.i5.know02.artifacts import (
    add_artifact_version,
    link_evidence,
    mark_version_state,
    upsert_artifact,
    upsert_claim_detail,
)
from backend.app.services.i5.know02.eligibility import runtime_evidence_allowed
from backend.app.services.i5.know02.seed_fixtures import seed_know02_foundation
from backend.app.services.i5.know02.taxonomy import link_ku_concept, link_ku_dimension
from backend.app.services.i5.enums import ArtifactType, ArtifactVersionState, ClaimClass
from backend.app.services.i5.know03.effects import add_effect_estimate
from backend.app.services.i5.know03.recommendations import (
    link_recommendation_condition,
    link_recommendation_evidence,
    supersede_recommendation,
    upsert_recommendation,
)
from backend.app.services.i5.know03.studies import (
    add_population_criterion,
    link_study_artifact,
    link_study_condition,
    link_study_intervention,
    link_study_outcome,
    map_intervention,
    upsert_clinical_study,
    upsert_intervention,
    upsert_outcome,
    upsert_population,
)
from backend.app.services.i5.know03.terminology import seed_terminology_contracts


def _ku(db: Session, canonical: str, statement: str, domain: str) -> models.KnowledgeUnit:
    from backend.app.services.i5.know02.seed_fixtures import _make_ku

    return _make_ku(db, canonical=canonical, statement=statement, domain=domain)


def seed_know03_foundation(db: Session) -> Dict[str, Any]:
    base = seed_know02_foundation(db)
    term_n = seed_terminology_contracts(db)

    als = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:als").one()
    ms = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:ms").one()
    t2 = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:diabetes:t2").one()
    rrms = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:ms:rrms").one()
    healthy = db.query(models.I5ClinicalConcept).filter_by(concept_key="population:healthy").one()
    htn = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:hypertension").one()
    asthma = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:asthma").one()
    depression = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:major_depression").one()
    ckd = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:ckd").one()
    breast = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:breast_cancer").one()
    flu = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:influenza").one()
    osa = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:osa").one()

    # Osteoarthritis (additional non-P0 family)
    oa = (
        db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:osteoarthritis").first()
    )
    if oa is None:
        from backend.app.services.i5.know02.taxonomy import upsert_concept
        from backend.app.services.i5.enums import ClinicalConceptType, SediRootCategory

        oa = upsert_concept(
            db,
            concept_key="disease:osteoarthritis",
            preferred_name="Osteoarthritis",
            concept_type=ClinicalConceptType.DISEASE.value,
            root_category=SediRootCategory.MUSCULOSKELETAL.value,
        )

    gsp = db.query(models.GovernedSourceProfile).filter_by(canonical_key="know02:fixture_publisher").one()

    # Shared interventions / outcomes
    niv = upsert_intervention(
        db,
        intervention_key="int:respiratory_support_niv",
        preferred_name="Noninvasive ventilatory support",
        intervention_category=InterventionCategory.RESPIRATORY_SUPPORT.value,
    )
    map_intervention(
        db,
        intervention_id=niv.id,
        terminology_system=TerminologySystem.ICHI.value,
        external_code="ICHI-FIX-RESP",
        provenance_note="BOUNDED_FIXTURE placeholder",
    )
    soc = upsert_intervention(
        db,
        intervention_key="int:standard_of_care",
        preferred_name="Standard of care",
        intervention_category=InterventionCategory.OTHER.value,
    )
    exercise = upsert_intervention(
        db,
        intervention_key="int:structured_exercise",
        preferred_name="Structured exercise program",
        intervention_category=InterventionCategory.EXERCISE.value,
    )
    diet = upsert_intervention(
        db,
        intervention_key="int:medical_nutrition",
        preferred_name="Medical nutrition therapy",
        intervention_category=InterventionCategory.DIET.value,
    )
    metformin = upsert_intervention(
        db,
        intervention_key="int:metformin",
        preferred_name="Metformin",
        intervention_category=InterventionCategory.DRUG.value,
    )
    map_intervention(
        db,
        intervention_id=metformin.id,
        terminology_system=TerminologySystem.RXNORM.value,
        external_code="6809",
        provenance_note="BOUNDED RxNorm fixture code slot",
    )
    rehab = upsert_intervention(
        db,
        intervention_key="int:rehab_physio",
        preferred_name="Physiotherapy rehabilitation",
        intervention_category=InterventionCategory.REHABILITATION.value,
    )
    lifestyle = upsert_intervention(
        db,
        intervention_key="int:lifestyle_counseling",
        preferred_name="Lifestyle counseling",
        intervention_category=InterventionCategory.LIFESTYLE.value,
    )
    sleep_hygiene = upsert_intervention(
        db,
        intervention_key="int:sleep_hygiene",
        preferred_name="Sleep hygiene routine",
        intervention_category=InterventionCategory.BEHAVIORAL.value,
    )
    cbt = upsert_intervention(
        db,
        intervention_key="int:cbt",
        preferred_name="Cognitive behavioural therapy",
        intervention_category=InterventionCategory.PSYCHOLOGICAL.value,
    )
    routine = upsert_intervention(
        db,
        intervention_key="int:daily_routine_structure",
        preferred_name="Daily routine structuring",
        intervention_category=InterventionCategory.SELF_CARE.value,
    )

    alsfrs = upsert_outcome(
        db,
        outcome_key="out:alsfrs_r",
        preferred_name="ALSFRS-R",
        outcome_category=OutcomeCategory.FUNCTION.value,
        measurement_scale="ALSFRS-R",
        direction_of_benefit=OutcomeDirectionOfBenefit.HIGHER_BETTER.value,
    )
    fvc = upsert_outcome(
        db,
        outcome_key="out:fvc",
        preferred_name="Forced vital capacity",
        outcome_category=OutcomeCategory.FUNCTION.value,
        unit="% predicted",
        direction_of_benefit=OutcomeDirectionOfBenefit.HIGHER_BETTER.value,
    )
    ae = upsert_outcome(
        db,
        outcome_key="out:serious_ae",
        preferred_name="Serious adverse event",
        outcome_category=OutcomeCategory.ADVERSE_EVENT.value,
        direction_of_benefit=OutcomeDirectionOfBenefit.LOWER_BETTER.value,
    )
    relapse = upsert_outcome(
        db,
        outcome_key="out:arr",
        preferred_name="Annualized relapse rate",
        outcome_category=OutcomeCategory.RELAPSE.value,
        direction_of_benefit=OutcomeDirectionOfBenefit.LOWER_BETTER.value,
    )
    edss = upsert_outcome(
        db,
        outcome_key="out:edss",
        preferred_name="EDSS",
        outcome_category=OutcomeCategory.DISABILITY.value,
        direction_of_benefit=OutcomeDirectionOfBenefit.LOWER_BETTER.value,
    )
    hba1c = upsert_outcome(
        db,
        outcome_key="out:hba1c",
        preferred_name="HbA1c",
        outcome_category=OutcomeCategory.LAB.value,
        unit="%",
        direction_of_benefit=OutcomeDirectionOfBenefit.LOWER_BETTER.value,
    )
    # LOINC-style outcome concept note via terminology contract only

    # --- ALS study ---
    als_art = upsert_artifact(
        db,
        artifact_key="fixture:know03:als_resp_rct",
        artifact_type=ArtifactType.RCT.value,
        title="ALS respiratory supportive care RCT (fixture)",
        source_profile_id=gsp.id,
        pmid="8800001",
    )
    als_v = add_artifact_version(db, artifact_id=als_art.id, version_label="1", content_hash="a" * 64)
    als_study = upsert_clinical_study(
        db,
        study_key="study:know03:als_resp",
        study_design=StudyDesign.RANDOMIZED_CONTROLLED_TRIAL.value,
        primary_artifact_id=als_art.id,
        primary_artifact_version_id=als_v.id,
        registry_identifier="NCT-FIX-ALS-001",
        title="ALS respiratory support fixture trial",
        sample_size=120,
        randomized=True,
        controlled=True,
        study_status="COMPLETED",
        risk_of_bias="SOME_CONCERNS",
    )
    link_study_artifact(
        db, study_id=als_study.id, artifact_version_id=als_v.id, artifact_role=StudyArtifactRole.PRIMARY_RESULTS.value
    )
    link_study_condition(db, study_id=als_study.id, concept_id=als.id)
    als_pop = upsert_population(
        db,
        study_id=als_study.id,
        population_key="adult_als",
        sample_size=120,
        age_min_years=18,
        inclusion_criteria_text="Adults with ALS",
    )
    add_population_criterion(
        db,
        population_id=als_pop.id,
        criterion_type=PopulationCriterionType.DIAGNOSIS.value,
        concept_id=als.id,
        operator="=",
        value_text="ALS",
    )
    add_population_criterion(
        db,
        population_id=als_pop.id,
        criterion_type=PopulationCriterionType.AGE.value,
        operator=">=",
        value_numeric=18,
        unit="years",
    )
    als_exp = link_study_intervention(
        db,
        study_id=als_study.id,
        intervention_id=niv.id,
        intervention_role=StudyInterventionRole.EXPERIMENTAL.value,
    )
    als_cmp = link_study_intervention(
        db,
        study_id=als_study.id,
        intervention_id=soc.id,
        intervention_role=StudyInterventionRole.COMPARATOR.value,
        comparator_kind=ComparatorKind.STANDARD_OF_CARE.value,
    )
    als_out = link_study_outcome(
        db, study_id=als_study.id, outcome_id=fvc.id, outcome_role=StudyOutcomeRole.PRIMARY.value, time_point="6 months"
    )
    als_harm = link_study_outcome(
        db, study_id=als_study.id, outcome_id=ae.id, outcome_role=StudyOutcomeRole.SAFETY.value, is_harm=True
    )
    add_effect_estimate(
        db,
        study_id=als_study.id,
        population_id=als_pop.id,
        study_intervention_id=als_exp.id,
        study_comparator_id=als_cmp.id,
        study_outcome_id=als_out.id,
        effect_measure=EffectMeasure.MEAN_DIFFERENCE.value,
        effect_value=4.2,
        ci_lower=1.0,
        ci_upper=7.4,
        confidence_level=95,
        sample_size_analyzed=118,
        follow_up_duration=6,
        follow_up_unit="months",
        statistical_significance="SIGNIFICANT",
        clinical_significance="SOURCE_STATED",
    )
    add_effect_estimate(
        db,
        study_id=als_study.id,
        study_outcome_id=als_harm.id,
        study_intervention_id=als_exp.id,
        study_comparator_id=als_cmp.id,
        effect_measure=EffectMeasure.RISK_RATIO.value,
        effect_value=1.1,
        ci_lower=0.7,
        ci_upper=1.7,
        confidence_level=95,
        sample_size_analyzed=120,
        event_count_intervention=12,
        event_count_comparator=11,
        statistical_significance="NOT_SIGNIFICANT",
        clinical_significance="NOT_REPORTED",
        notes="harms preserved alongside benefits",
    )
    ku_als = _ku(
        db,
        "know03:claim:als_resp",
        "Supportive respiratory intervention associated with FVC change in ALS (fixture).",
        "neurology",
    )
    link_ku_concept(db, knowledge_unit_id=ku_als.id, concept_id=als.id)
    link_ku_dimension(db, knowledge_unit_id=ku_als.id, dimension_code=KnowledgeDimensionCode.RESPIRATORY_CARE.value)
    upsert_claim_detail(
        db, knowledge_unit_id=ku_als.id, claim_class=ClaimClass.INTERVENTION_EFFECT.value, subject_concept_id=als.id
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_als.id,
        artifact_version_id=als_v.id,
        support_direction=EvidenceSupportDirection.SUPPORTS.value,
        study_id=als_study.id,
        enforce_runtime_support=True,
    )

    # Guideline recommendation ALS (separate from study)
    gl1 = upsert_artifact(
        db,
        artifact_key="fixture:know03:als_guideline_v1",
        artifact_type=ArtifactType.GUIDELINE.value,
        title="ALS care guideline v1 (fixture)",
        source_profile_id=gsp.id,
        guideline_id="FIX-ALS-GL-1",
    )
    gl1v = add_artifact_version(db, artifact_id=gl1.id, version_label="2023", content_hash="b" * 64)
    gl2v = add_artifact_version(
        db, artifact_id=gl1.id, version_label="2025", content_hash="c" * 64, supersedes_version_id=gl1v.id
    )
    mark_version_state(db, version_id=gl1v.id, version_state=ArtifactVersionState.SUPERSEDED.value)
    rec1 = upsert_recommendation(
        db,
        recommendation_key="rec:als:resp:v1",
        source_artifact_version_id=gl1v.id,
        recommended_action="Consider noninvasive ventilation assessment in ALS with respiratory decline",
        recommendation_direction=RecommendationDirection.CONDITIONAL.value,
        grading_system="SOURCE_NATIVE",
        original_grade="Conditional",
        status=RecommendationStatus.CURRENT.value,
        target_population_text="adults with ALS",
        monitoring_requirements="Monitor respiratory function",
        harm_summary="Device intolerance possible",
    )
    link_recommendation_condition(db, recommendation_id=rec1.id, concept_id=als.id)
    link_recommendation_evidence(
        db,
        recommendation_id=rec1.id,
        target_kind=RecommendationEvidenceTargetKind.CLINICAL_STUDY.value,
        study_id=als_study.id,
    )
    rec2 = upsert_recommendation(
        db,
        recommendation_key="rec:als:resp:v2",
        source_artifact_version_id=gl2v.id,
        recommended_action="Offer timely respiratory support assessment in ALS",
        recommendation_direction=RecommendationDirection.SUGGEST.value,
        grading_system="SOURCE_NATIVE",
        original_grade="Suggest",
        status=RecommendationStatus.CURRENT.value,
    )
    link_recommendation_condition(db, recommendation_id=rec2.id, concept_id=als.id)
    supersede_recommendation(db, old_recommendation_id=rec1.id, new_recommendation_id=rec2.id)

    # --- MS study + conflict set ---
    ms_art = upsert_artifact(
        db,
        artifact_key="fixture:know03:ms_exercise_rct",
        artifact_type=ArtifactType.RCT.value,
        title="MS exercise RCT (fixture)",
        source_profile_id=gsp.id,
        pmid="8800002",
    )
    ms_v = add_artifact_version(db, artifact_id=ms_art.id, version_label="1", content_hash="d" * 64)
    ms_study = upsert_clinical_study(
        db,
        study_key="study:know03:ms_exercise",
        study_design=StudyDesign.RANDOMIZED_CONTROLLED_TRIAL.value,
        primary_artifact_version_id=ms_v.id,
        primary_artifact_id=ms_art.id,
        sample_size=80,
        randomized=True,
        study_status="COMPLETED",
    )
    link_study_condition(db, study_id=ms_study.id, concept_id=ms.id)
    link_study_condition(
        db, study_id=ms_study.id, concept_id=rrms.id, condition_role=StudyConditionRole.PRIMARY_CONDITION.value
    )
    ms_pop = upsert_population(db, study_id=ms_study.id, population_key="rrms_adults", sample_size=80)
    add_population_criterion(
        db, population_id=ms_pop.id, criterion_type=PopulationCriterionType.SUBTYPE.value, concept_id=rrms.id
    )
    ms_exp = link_study_intervention(
        db, study_id=ms_study.id, intervention_id=exercise.id, intervention_role=StudyInterventionRole.EXPERIMENTAL.value
    )
    ms_cmp = link_study_intervention(
        db,
        study_id=ms_study.id,
        intervention_id=soc.id,
        intervention_role=StudyInterventionRole.COMPARATOR.value,
        comparator_kind=ComparatorKind.STANDARD_OF_CARE.value,
    )
    ms_out = link_study_outcome(db, study_id=ms_study.id, outcome_id=edss.id)
    add_effect_estimate(
        db,
        study_id=ms_study.id,
        study_outcome_id=ms_out.id,
        study_intervention_id=ms_exp.id,
        study_comparator_id=ms_cmp.id,
        effect_measure=EffectMeasure.MEAN_DIFFERENCE.value,
        effect_value=-0.3,
        ci_lower=-0.6,
        ci_upper=0.0,
        confidence_level=95,
        statistical_significance="SIGNIFICANT",
        clinical_significance="UNCERTAIN",
    )
    # Conflicting SR
    sr = upsert_artifact(
        db,
        artifact_key="fixture:know03:ms_exercise_sr_contra",
        artifact_type=ArtifactType.SYSTEMATIC_REVIEW.value,
        title="MS exercise SR contradicting (fixture)",
        source_profile_id=gsp.id,
        pmid="8800003",
    )
    sr_v = add_artifact_version(db, artifact_id=sr.id, version_label="1", content_hash="e" * 64)
    ku_ms = _ku(db, "know03:claim:ms_exercise", "MS exercise effect contested (fixture).", "neurology")
    link_ku_concept(db, knowledge_unit_id=ku_ms.id, concept_id=ms.id)
    link_ku_dimension(db, knowledge_unit_id=ku_ms.id, dimension_code=KnowledgeDimensionCode.EXERCISE.value)
    link_evidence(
        db,
        knowledge_unit_id=ku_ms.id,
        artifact_version_id=ms_v.id,
        support_direction=EvidenceSupportDirection.SUPPORTS.value,
        study_id=ms_study.id,
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_ms.id,
        artifact_version_id=sr_v.id,
        support_direction=EvidenceSupportDirection.CONTRADICTS.value,
    )
    ms_gl = upsert_artifact(
        db,
        artifact_key="fixture:know03:ms_guideline",
        artifact_type=ArtifactType.GUIDELINE.value,
        title="MS exercise guideline (fixture)",
        source_profile_id=gsp.id,
        guideline_id="FIX-MS-EX",
    )
    ms_gl_v = add_artifact_version(db, artifact_id=ms_gl.id, version_label="1", content_hash="f" * 64)
    ms_rec = upsert_recommendation(
        db,
        recommendation_key="rec:ms:exercise:conditional",
        source_artifact_version_id=ms_gl_v.id,
        recommended_action="Conditional structured exercise in MS",
        recommendation_direction=RecommendationDirection.CONDITIONAL.value,
    )
    link_recommendation_condition(db, recommendation_id=ms_rec.id, concept_id=ms.id)
    link_recommendation_evidence(
        db,
        recommendation_id=ms_rec.id,
        target_kind=RecommendationEvidenceTargetKind.ARTIFACT_VERSION.value,
        artifact_version_id=ms_v.id,
    )
    # Conflicting recommend-against from another guideline (both remain)
    ms_gl_b = upsert_artifact(
        db,
        artifact_key="fixture:know03:ms_guideline_against",
        artifact_type=ArtifactType.GUIDELINE.value,
        title="MS exercise caution guideline (fixture)",
        source_profile_id=gsp.id,
        guideline_id="FIX-MS-EX-B",
    )
    ms_gl_b_v = add_artifact_version(db, artifact_id=ms_gl_b.id, version_label="1", content_hash="11" * 32)
    ms_rec_against = upsert_recommendation(
        db,
        recommendation_key="rec:ms:exercise:against_unsupervised",
        source_artifact_version_id=ms_gl_b_v.id,
        recommended_action="Recommend against unsupervised high-intensity exercise in unstable MS",
        recommendation_direction=RecommendationDirection.RECOMMEND_AGAINST.value,
    )
    link_recommendation_condition(db, recommendation_id=ms_rec_against.id, concept_id=ms.id)

    # --- T2DM nutrition + drug ---
    t2_art = upsert_artifact(
        db,
        artifact_key="fixture:know03:t2dm_nutrition",
        artifact_type=ArtifactType.OBSERVATIONAL_STUDY.value,
        title="T2DM nutrition cohort (fixture)",
        source_profile_id=gsp.id,
        pmid="8800004",
    )
    t2_v = add_artifact_version(db, artifact_id=t2_art.id, version_label="1", content_hash="g" * 64)
    t2_study = upsert_clinical_study(
        db,
        study_key="study:know03:t2dm_nutrition",
        study_design=StudyDesign.COHORT.value,
        primary_artifact_version_id=t2_v.id,
        primary_artifact_id=t2_art.id,
        sample_size=500,
    )
    link_study_condition(db, study_id=t2_study.id, concept_id=t2.id)
    t2_pop = upsert_population(db, study_id=t2_study.id, population_key="adult_t2dm", sample_size=500)
    t2_exp = link_study_intervention(
        db, study_id=t2_study.id, intervention_id=diet.id, intervention_role=StudyInterventionRole.EXPERIMENTAL.value
    )
    t2_out = link_study_outcome(db, study_id=t2_study.id, outcome_id=hba1c.id, time_point="12 months")
    add_effect_estimate(
        db,
        study_id=t2_study.id,
        population_id=t2_pop.id,
        study_intervention_id=t2_exp.id,
        study_outcome_id=t2_out.id,
        effect_measure=EffectMeasure.MEAN_DIFFERENCE.value,
        effect_value=-0.5,
        ci_lower=-0.8,
        ci_upper=-0.2,
        confidence_level=95,
        statistical_significance="SIGNIFICANT",
        clinical_significance="NOT_REPORTED",
    )
    drug_study = upsert_clinical_study(
        db,
        study_key="study:know03:t2dm_metformin",
        study_design=StudyDesign.RANDOMIZED_CONTROLLED_TRIAL.value,
        sample_size=200,
        randomized=True,
        controlled=True,
    )
    link_study_condition(db, study_id=drug_study.id, concept_id=t2.id)
    link_study_intervention(
        db,
        study_id=drug_study.id,
        intervention_id=metformin.id,
        intervention_role=StudyInterventionRole.EXPERIMENTAL.value,
        dose="1000",
        dose_unit="mg",
        frequency="BID",
    )
    t2_gl = upsert_artifact(
        db,
        artifact_key="fixture:know03:ada_nutrition",
        artifact_type=ArtifactType.GUIDELINE.value,
        title="Diabetes nutrition guideline (fixture)",
        source_profile_id=gsp.id,
        guideline_id="FIX-DM-NUT",
    )
    t2_gl_v = add_artifact_version(db, artifact_id=t2_gl.id, version_label="1", content_hash="h" * 64)
    t2_rec = upsert_recommendation(
        db,
        recommendation_key="rec:t2dm:nutrition",
        source_artifact_version_id=t2_gl_v.id,
        recommended_action="Individualized medical nutrition therapy for type 2 diabetes",
        recommendation_direction=RecommendationDirection.RECOMMEND.value,
        grading_system="ADA-like-fixture",
        original_grade="A",
        normalized_strength="STRONG_PROVISIONAL",
    )
    link_recommendation_condition(db, recommendation_id=t2_rec.id, concept_id=t2.id)
    link_recommendation_evidence(
        db,
        recommendation_id=t2_rec.id,
        target_kind=RecommendationEvidenceTargetKind.CLINICAL_STUDY.value,
        study_id=t2_study.id,
    )

    # Lifestyle / care dimensions across diseases
    for key, concept, intervention, dim, design in (
        ("study:know03:oa_rehab", oa, rehab, KnowledgeDimensionCode.REHABILITATION.value, StudyDesign.NONRANDOMIZED_TRIAL.value),
        ("study:know03:htn_lifestyle", htn, lifestyle, KnowledgeDimensionCode.LIFESTYLE.value, StudyDesign.COHORT.value),
        ("study:know03:osa_sleep", osa, sleep_hygiene, KnowledgeDimensionCode.SLEEP.value, StudyDesign.CROSS_SECTIONAL.value),
        ("study:know03:dep_mental", depression, cbt, KnowledgeDimensionCode.MENTAL_HEALTH.value, StudyDesign.RANDOMIZED_CONTROLLED_TRIAL.value),
        ("study:know03:healthy_routine", healthy, routine, KnowledgeDimensionCode.DAILY_ROUTINE.value, StudyDesign.OTHER.value),
        ("study:know03:asthma_exercise", asthma, exercise, KnowledgeDimensionCode.EXERCISE.value, StudyDesign.COHORT.value),
        ("study:know03:ckd_nutrition", ckd, diet, KnowledgeDimensionCode.NUTRITION.value, StudyDesign.COHORT.value),
        ("study:know03:breast_lifestyle", breast, lifestyle, KnowledgeDimensionCode.LIFESTYLE.value, StudyDesign.OTHER.value),
        ("study:know03:flu_prevention", flu, lifestyle, KnowledgeDimensionCode.PREVENTION.value, StudyDesign.OTHER.value),
    ):
        st = upsert_clinical_study(db, study_key=key, study_design=design, sample_size=50, study_status="COMPLETED")
        link_study_condition(
            db,
            study_id=st.id,
            concept_id=concept.id,
            condition_role=(
                StudyConditionRole.PREVENTION_TARGET.value
                if concept.id == healthy.id or "prevention" in key
                else StudyConditionRole.PRIMARY_CONDITION.value
            ),
        )
        link_study_intervention(
            db, study_id=st.id, intervention_id=intervention.id, intervention_role=StudyInterventionRole.EXPERIMENTAL.value
        )
        ku = _ku(db, f"know03:claim:{key.split(':')[-1]}", f"Fixture claim for {key}", "general")
        link_ku_concept(db, knowledge_unit_id=ku.id, concept_id=concept.id)
        link_ku_dimension(db, knowledge_unit_id=ku.id, dimension_code=dim)

    # Retracted primary study version remains historical; runtime eligibility false
    ret_art = upsert_artifact(
        db,
        artifact_key="fixture:know03:retracted_primary",
        artifact_type=ArtifactType.ARTICLE.value,
        title="Retracted primary (fixture)",
        source_profile_id=gsp.id,
        pmid="8800099",
    )
    ret_v = add_artifact_version(db, artifact_id=ret_art.id, version_label="1", content_hash="i" * 64)
    mark_version_state(db, version_id=ret_v.id, version_state=ArtifactVersionState.RETRACTED.value)
    ret_study = upsert_clinical_study(
        db,
        study_key="study:know03:retracted",
        study_design=StudyDesign.CASE_SERIES.value,
        primary_artifact_version_id=ret_v.id,
        primary_artifact_id=ret_art.id,
    )
    assert runtime_evidence_allowed(ret_v) is False

    # Insufficient evidence recommendation
    insuff = upsert_recommendation(
        db,
        recommendation_key="rec:general:insufficient",
        source_artifact_version_id=t2_gl_v.id,
        recommended_action="Evidence insufficient for intervention X in population Y",
        recommendation_direction=RecommendationDirection.INSUFFICIENT_EVIDENCE.value,
        contraindications="Not applicable — insufficient evidence",
    )

    db.flush()
    return {
        **base,
        "terminology_contracts": term_n,
        "studies": {
            "als": als_study.id,
            "ms": ms_study.id,
            "t2dm": t2_study.id,
            "retracted": ret_study.id,
        },
        "recommendations": {
            "als_v1": rec1.id,
            "als_v2": rec2.id,
            "ms_conditional": ms_rec.id,
            "ms_against": ms_rec_against.id,
            "t2dm": t2_rec.id,
            "insufficient": insuff.id,
        },
        "icd11_full_import": "NEXT_TERMINOLOGY_WAVE",
        "p0_specific_branching_in_core_study_model": 0,
        "silent_content_drift": 0,
    }
