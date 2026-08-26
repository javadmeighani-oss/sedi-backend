"""I5-KNOW-06 — frozen patient↔evidence applicability contract (I5 design ownership only).

Runtime personal-context projection / matching / recommendation integration is owned by
I6/I7/I8 per frozen authority. This package MUST NOT persist personal clinical SoTs.
"""

from __future__ import annotations

PACKAGE_ID = "I5-KNOW-06"
CONTRACT_CLOSED = True
RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5 = False
RUNTIME_OWNER = "I6/I7/I8_INTEGRATION"
I5_RUNTIME_PERSONALIZATION_IMPLEMENTED = False

AUTHORITY_DOCS = (
    "docs/architecture/i5-final-knowledge-architecture-freeze-01/07_PATIENT_EVIDENCE_APPLICABILITY.md",
    "docs/architecture/i5-final-knowledge-architecture-freeze-01/09_REMAINING_SCOPE_IMPLEMENTATION_WAVES.md",
)

# ---------------------------------------------------------------------------
# Ownership boundary (frozen)
# ---------------------------------------------------------------------------

I5_OWNERSHIP = frozenset(
    {
        "scientific_evidence_contract",
        "applicability_criteria_vocabulary",
        "safe_output_states",
        "forbidden_output_states",
        "provenance_lineage_requirements",
        "cross_layer_interface_expectations",
    }
)

I6_OWNERSHIP = frozenset(
    {
        "canonical_personal_memory",
        "personal_context",
        "memory_writes",
        "clinical_feature_projection_runtime",
        "lineage_backed_feature_reads",
    }
)

I7_OWNERSHIP = frozenset(
    {
        "longitudinal_user_intelligence",
        "longitudinal_context_for_applicability",
    }
)

I8_OWNERSHIP = frozenset(
    {
        "personalized_evidence_applicability_runtime",
        "user_evidence_match_runtime",
        "grounded_recommendation_intelligence",
        "recommendation_plan_consumption",
    }
)

I5_PERSONAL_MEMORY_WRITE = False
I5_CANONICAL_USER_RECORD = False
I5_USER_PROFILE_MUTATION = False
I5_RUNTIME_PERSONAL_DECISION_OWNER = False

# ---------------------------------------------------------------------------
# user_clinical_feature_index (derived projection contract — not I5 table)
# ---------------------------------------------------------------------------

USER_CLINICAL_FEATURE_INDEX_FIELDS = (
    "user_id",
    "feature_concept_id",
    "value",
    "unit",
    "observed_at",
    "source_record_type",
    "source_record_id",
    "verification_state",
    "confidence",
)

# ---------------------------------------------------------------------------
# evidence_applicability_rules input vocabulary (frozen)
# ---------------------------------------------------------------------------

APPLICABILITY_INPUT_FEATURES = (
    "diagnosis",
    "subtype",
    "phenotype",
    "stage",
    "age",
    "sex",
    "genotype",
    "biomarker",
    "lab_threshold",
    "prior_current_treatment",
    "comorbidity",
    "contraindication",
    "renal_hepatic",
    "pregnancy",
    "functional_score",
    "disease_duration",
)

APPLICABILITY_RULE_FIELDS = (
    "required_features",
    "optional_features",
    "missing_required_features",
)

# ---------------------------------------------------------------------------
# user_evidence_matches output contract (frozen)
# ---------------------------------------------------------------------------

USER_EVIDENCE_MATCH_FIELDS = (
    "population_match",
    "disease_match",
    "phenotype_match",
    "biomarker_match",
    "treatment_context_match",
    "evidence_strength",
    "directness",
    "freshness",
    "contraindication_status",
    "medical_safety_state",
    "missing_required_features",
    "overall_applicability",
    "transparent_match_explanation",
)

USER_EVIDENCE_MATCH_LINEAGE_FIELDS = (
    "evidence_ku_id",
    "feature_lineage_refs",
)

# ---------------------------------------------------------------------------
# Safe / forbidden overall_applicability states (frozen)
# ---------------------------------------------------------------------------

SAFE_APPLICABILITY_STATES = frozenset(
    {
        "GUIDELINE_ALIGNED_OPTION",
        "EVIDENCE_SUPPORTED_OPTION",
        "EVIDENCE_MAY_BE_RELEVANT",
        "EMERGING_EVIDENCE",
        "EXPERIMENTAL_ONLY",
        "CLINICAL_TRIAL_POTENTIAL_MATCH",
        "CONFLICTING_EVIDENCE",
        "INSUFFICIENT_EVIDENCE",
        "NOT_APPLICABLE",
        "POTENTIAL_CONTRAINDICATION",
        "SPECIALIST_REVIEW_REQUIRED",
    }
)

FORBIDDEN_APPLICABILITY_STATES = frozenset(
    {
        "CURE_FOUND",
        "TREATMENT_FOUND",
        "TAKE_THIS_DRUG",
        "STOP_CURRENT_TREATMENT",
    }
)

# Synonyms that must not silently bypass forbidden semantics.
FORBIDDEN_STATE_SYNONYMS = frozenset(
    {
        "CURE",
        "CURED",
        "TREATMENT_FOUND",
        "FOUND_TREATMENT",
        "TAKE_THIS",
        "TAKE_DRUG",
        "STOP_TREATMENT",
        "STOP_MEDICATION",
        "PRESCRIBE_THIS",
    }
)

FAIL_CLOSED_OVERALL_STATES = frozenset(
    {
        "INSUFFICIENT_EVIDENCE",
        "NOT_APPLICABLE",
        "POTENTIAL_CONTRAINDICATION",
        "SPECIALIST_REVIEW_REQUIRED",
        "CONFLICTING_EVIDENCE",
    }
)

CONTRAINDICATION_FAIL_CLOSED_STATUSES = frozenset(
    {
        "PRESENT",
        "SUSPECTED",
        "UNVERIFIED_SIGNAL",
    }
)
