# 05 — Structured Clinical Evidence Data Model (FROZEN)

```text
KU_FOUNDATION = KEEP (do not replace KnowledgeUnit)
PRIMARY_PROVENANCE = KEEP KnowledgeProvenance 1:1 as primary citation anchor
MULTI_EVIDENCE = NEW knowledge_unit_evidence_links (N:M)
DESIGN_ONLY = YES — no ORM/migration in this Gate
```

## Epistemic separation (FROZEN)

```text
SCIENTIFIC_FINDING
CLINICAL_RECOMMENDATION
GUIDELINE_RECOMMENDATION
CONSENSUS
EXPERIMENTAL_HYPOTHESIS
REGULATORY_STATUS
```

A paper ≠ automatic clinical recommendation.

## Scientific artifacts

```text
scientific_artifacts
scientific_artifact_versions
```

Types: ARTICLE, SYSTEMATIC_REVIEW, META_ANALYSIS, GUIDELINE, CONSENSUS_STATEMENT, RCT, OBSERVATIONAL_STUDY, CASE_SERIES, CASE_REPORT, BOOK, BOOK_CHAPTER, REGULATORY_DOCUMENT, DRUG_LABEL, CLINICAL_TRIAL_RECORD, DATASET, OTHER.

IDs: DOI, PMID, PMCID, ISBN, NCT_ID, GUIDELINE_ID, publisher_id, canonical_URL.

## Proposed table matrix

| table | purpose | PK | key FKs | cardinality | class | V1? | why necessary |
|---|---|---|---|---|---|---|---|
| governed_source_profiles | trusted source identity | id | — | 1 | **EXTEND_EXISTING** | Y | registry base |
| governed_source_profile_versions | immutable source versions | id | gsp_id | N:1 | **REUSE_EXISTING** | Y | provenance |
| i5_source_registry_extensions | registry overlay fields | gsp_id | gsp | 1:1 | **NEW_REQUIRED** | Y | rights/endpoints without bloating core GSP unchecked |
| i5_reference_books | book registry | id | publisher_gsp? | 1 | **NEW_REQUIRED** | Y | books ≠ sources |
| i5_reference_book_editions | editions | id | book_id | N:1 | **NEW_REQUIRED** | Y | supersession |
| scientific_artifacts | durable artifact identity | id | source_profile_id | 1 | **NEW_REQUIRED** | Y | DOI/PMID/NCT identity |
| scientific_artifact_versions | immutable artifact versions | id | artifact_id | N:1 | **NEW_REQUIRED** | Y | version provenance |
| i5_raw_evidence | raw/transient evidence | id | — | 1 | **REUSE_EXISTING** | Y | bytes policy |
| knowledge_units | claims/guidance units | id | — | 1 | **REUSE_EXISTING** | Y | foundation |
| knowledge_provenance | **primary** 1:1 provenance | id | ku_id UNIQUE | 1:1 | **REUSE_EXISTING** | Y | W1/SCIS contracts |
| knowledge_unit_evidence_links | multi-evidence N:M | id | ku_id, artifact_version_id | N:M | **NEW_REQUIRED** | Y | multi-evidence requirement |
| clinical_concepts | concept dictionary | id | — | 1 | **NEW_REQUIRED** | Y | interoperability |
| clinical_concept_mappings | external code maps | id | concept_id | N:1 | **NEW_REQUIRED** | Y | ICD/MeSH/… |
| clinical_studies | study records | id | artifact_version_id | 1 | **NEW_REQUIRED** | Y | structured study |
| study_populations | populations | id | study_id | N:1 | **NEW_REQUIRED** | Y | applicability |
| interventions | intervention dictionary | id | concept_id? | 1 | **NEW_REQUIRED** | Y | normalize Rx |
| study_interventions | study↔intervention | id | study, intervention | N:M | **NEW_REQUIRED** | Y | |
| clinical_outcomes | outcome dictionary | id | concept_id? | 1 | **NEW_REQUIRED** | Y | |
| study_outcomes | study outcomes | id | study, outcome | N:M | **NEW_REQUIRED** | Y | |
| study_effect_estimates | numeric effects | id | study_outcome_id | N:1 | **NEW_REQUIRED** | Y | avoid LLM re-parse |
| knowledge_claim_details | structured claim facets | id | ku_id | 1:1/N | **NEW_REQUIRED** | Y | claim typing |
| clinical_recommendations | guideline/rec objects | id | ku_id?, artifact_version_id | 1 | **NEW_REQUIRED** | Y | rec ≠ finding |
| clinical_trials | CT.gov structured | id | nct_id UNIQUE | 1 | **NEW_REQUIRED** | Y | API v2 |
| clinical_trial_conditions | trial conditions | id | trial_id | N:1 | **NEW_REQUIRED** | Y | |
| clinical_trial_interventions | trial interventions | id | trial_id | N:1 | **NEW_REQUIRED** | Y | |
| clinical_trial_outcomes | trial outcomes | id | trial_id | N:1 | **NEW_REQUIRED** | Y | |
| clinical_trial_eligibility | eligibility criteria | id | trial_id | N:1 | **NEW_REQUIRED** | Y | future match |
| clinical_trial_locations | sites | id | trial_id | N:1 | **OPTIONAL_POST_V1** | N | location UX later |
| user_clinical_feature_index | derived projection | id | user_id | N:1 | **NEW_REQUIRED** | Y* | *read path; I6 write ownership later |
| evidence_applicability_rules | rule defs | id | — | 1 | **NEW_REQUIRED** | Y | |
| user_evidence_matches | match results | id | user_id, ku/evidence | N | **NEW_REQUIRED** | Y | transparent match |
| knowledge_coverage_cells | Disease×Dim×Class×Tier×Fresh | id | — | 1 | **NEW_REQUIRED** | Y | measurable coverage |
| knowledge_gaps | gaps | id | — | 1 | **REUSE_EXISTING** | Y | generated from cells |
| knowledge_chunk_embeddings | SCIS index | id | chunk/ku | N | **REUSE_EXISTING** | Y | disposable index |
| knowledge_sources (legacy) | Gate3 companion | id | — | 1 | **REUSE_EXISTING** | Y | not crawler SoT |
| iran_* | local directory | id | — | 1 | **REUSE_EXISTING** | Y | NOT clinical KU |
| duplicate claim blob tables | — | — | — | — | **REJECTED_AS_REDUNDANT** | — | use KU + claim_details |

### knowledge_unit_evidence_links columns (FROZEN)

```text
evidence_role, support_direction ∈ {SUPPORTS, WEAKLY_SUPPORTS, NEUTRAL, CONTRADICTS, REFUTES, INCONCLUSIVE}
artifact_version_id, study_id nullable
locator (section/page/table/figure/paragraph)
directness, certainty, quality, support_score
retrieved_at
```

Primary `KnowledgeProvenance` remains for W1 completeness / SCIS citation anchor; links provide multi-evidence graph.

## Effect estimates (nullable-aware)

```text
intervention, comparator, outcome
effect_measure, effect_value, ci_lower, ci_upper, p_value
absolute_effect, relative_effect
follow_up_duration
statistical_significance, clinical_significance
sample_size
```

Missing fields allowed; never invent numerics.

## Recommendation object fields

```text
action, target_population, strength, certainty
benefits, harms, exceptions, contraindications, monitoring
jurisdiction, effective_period, guideline_source
```

## Terminology model

Concept classes: DISEASE, SUBTYPE, PHENOTYPE, SYMPTOM, SIGN, BIOMARKER, GENE, VARIANT, DRUG, INTERVENTION, PROCEDURE, DEVICE, LAB_TEST, IMAGING_FINDING, OUTCOME, COMPLICATION, RISK_FACTOR, ADVERSE_EVENT, CONTRAINDICATION.

External systems (subject to licensing): ICD-11, MeSH, RxNorm, LOINC, UMLS, SNOMED CT where authorized, DOI, PMID, PMCID, NCT.

**No proprietary terminology content hard-coded without rights review.**

## Indexes / versioning (design)

- Unique: artifact (doi), (pmid), (nct_id); concept_mappings (system, code)
- Versioning: artifact_versions immutable; KU immutable_version_id retained
- Retention: artifacts durable; raw per rights; index rebuildable
