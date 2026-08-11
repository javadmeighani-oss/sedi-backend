# 07 — Patient ↔ Evidence Applicability (FROZEN)

```text
PROJECTION != CANONICAL MEDICAL RECORD
LINEAGE_REQUIRED = YES
I6_OWNS_MEMORY_WRITES = YES (later)
```

## user_clinical_feature_index (derived)

```text
user_id, feature_concept_id, value, unit, observed_at
source_record_type, source_record_id
verification_state, confidence
```

Capable of projecting (when authorized/available): disease, subtype, phenotype, stage, symptoms, severity, genotype, biomarkers, labs, imaging, functional scales, medications, comorbidities, contraindications, pregnancy, age, sex, renal/hepatic, devices, lifestyle.

**Lineage sources (REUSE, do not duplicate SoT):** `user_conditions`, `user_medications`, `user_memory_facts`, `physiological_measurements`, profile tables, care episodes — never invent from LLM.

## evidence_applicability_rules

Criteria: diagnosis, subtype, phenotype, stage, age, sex, genotype, biomarker, lab threshold, prior/current treatment, comorbidity, contraindication, renal/hepatic, pregnancy, functional score, disease duration.

## user_evidence_matches

```text
population_match, disease_match, phenotype_match, biomarker_match, treatment_context_match
evidence_strength, directness, freshness
contraindication_status, medical_safety_state
missing_required_features[]
overall_applicability
transparent_match_explanation
```

## Safe output states (runtime future)

```text
GUIDELINE_ALIGNED_OPTION
EVIDENCE_SUPPORTED_OPTION
EVIDENCE_MAY_BE_RELEVANT
EMERGING_EVIDENCE
EXPERIMENTAL_ONLY
CLINICAL_TRIAL_POTENTIAL_MATCH
CONFLICTING_EVIDENCE
INSUFFICIENT_EVIDENCE
NOT_APPLICABLE
POTENTIAL_CONTRAINDICATION
SPECIALIST_REVIEW_REQUIRED
```

**Forbidden states:** CURE_FOUND, TREATMENT_FOUND, TAKE_THIS_DRUG, STOP_CURRENT_TREATMENT.
