"""I5-KNOW-06 patient↔evidence applicability contract closure tests (no persistence)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.i5.know06 import (
    APPLICABILITY_INPUT_FEATURES,
    AUTHORITY_DOCS,
    CONTRACT_CLOSED,
    FORBIDDEN_APPLICABILITY_STATES,
    I5_CANONICAL_USER_RECORD,
    I5_OWNERSHIP,
    I5_PERSONAL_MEMORY_WRITE,
    I5_RUNTIME_PERSONAL_DECISION_OWNER,
    I5_RUNTIME_PERSONALIZATION_IMPLEMENTED,
    I5_USER_PROFILE_MUTATION,
    I6_OWNERSHIP,
    I7_OWNERSHIP,
    I8_OWNERSHIP,
    RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5,
    RUNTIME_OWNER,
    SAFE_APPLICABILITY_STATES,
    USER_CLINICAL_FEATURE_INDEX_FIELDS,
    USER_EVIDENCE_MATCH_FIELDS,
)
from backend.app.services.i5.know06.cross_layer_matrix import (
    CROSS_LAYER_MATRIX,
    RUNTIME_INTEGRATION_GAPS,
)
from backend.app.services.i5.know06.sot_lineage import (
    DUPLICATE_SOT_CREATED,
    EXISTING_SOT_MAP,
    LLM_INVENTED_USER_FACT_PATH_ALLOWED,
    LINEAGE_REQUIRED,
)
from backend.app.services.i5.know06.validators import (
    Know06ContractError,
    assert_i5_ownership_boundary,
    build_insufficient_match,
    is_forbidden_applicability_state,
    reject_i5_personal_memory_write,
    reject_i5_user_profile_mutation,
    reject_llm_invented_user_fact,
    validate_applicability_rules,
    validate_feature_index_row,
    validate_safe_applicability_state,
    validate_user_evidence_match,
)
from backend.app.services.i8.constants import GOVERNED_DISEASE_APPLICABILITY_AVAILABLE


ROOT = Path(__file__).resolve().parents[2]


def test_frozen_authority_field_names_byte_present():
    auth = (ROOT / "docs/architecture/i5-final-knowledge-architecture-freeze-01/07_PATIENT_EVIDENCE_APPLICABILITY.md").read_text(
        encoding="utf-8"
    )
    for name in USER_CLINICAL_FEATURE_INDEX_FIELDS:
        assert name in auth
    for name in (
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
        "missing_required_features[]",
        "overall_applicability",
        "transparent_match_explanation",
    ):
        assert name in auth
    for state in SAFE_APPLICABILITY_STATES:
        assert state in auth
    for state in FORBIDDEN_APPLICABILITY_STATES:
        assert state in auth
    assert "I6_OWNS_MEMORY_WRITES = YES" in auth
    assert "never invent from LLM" in auth


def test_know06_wave_authority_not_i5_user_intelligence():
    waves = (
        ROOT / "docs/architecture/i5-final-knowledge-architecture-freeze-01/09_REMAINING_SCOPE_IMPLEMENTATION_WAVES.md"
    ).read_text(encoding="utf-8")
    assert "I5-KNOW-06" in waves
    assert "NOT I5-owned user intelligence" in waves
    assert "Implementation ownership is I6/I7/I8 integration" in waves


def test_contract_closed_flags():
    assert CONTRACT_CLOSED is True
    assert RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5 is False
    assert I5_RUNTIME_PERSONALIZATION_IMPLEMENTED is False
    assert RUNTIME_OWNER == "I6/I7/I8_INTEGRATION"
    assert I5_PERSONAL_MEMORY_WRITE is False
    assert I5_CANONICAL_USER_RECORD is False
    assert I5_USER_PROFILE_MUTATION is False
    assert I5_RUNTIME_PERSONAL_DECISION_OWNER is False
    assert GOVERNED_DISEASE_APPLICABILITY_AVAILABLE is False
    assert_i5_ownership_boundary()


def test_ownership_sets_disjoint_and_complete_enough():
    assert "scientific_evidence_contract" in I5_OWNERSHIP
    assert "memory_writes" in I6_OWNERSHIP
    assert "longitudinal_user_intelligence" in I7_OWNERSHIP
    assert "personalized_evidence_applicability_runtime" in I8_OWNERSHIP
    assert I5_OWNERSHIP.isdisjoint(I6_OWNERSHIP)
    assert I5_OWNERSHIP.isdisjoint(I8_OWNERSHIP)


def test_lineage_sot_map_reuses_existing_only():
    assert LINEAGE_REQUIRED is True
    assert DUPLICATE_SOT_CREATED is False
    assert LLM_INVENTED_USER_FACT_PATH_ALLOWED is False
    sources = {s.source for s in EXISTING_SOT_MAP}
    assert sources == {
        "user_conditions",
        "user_medications",
        "user_memory_facts",
        "physiological_measurements",
        "user_profile_core",
        "user_profile_knowledge",
        "care_episodes",
    }
    for s in EXISTING_SOT_MAP:
        assert s.lineage_id_available is True


def test_feature_index_requires_lineage_and_rejects_llm():
    row = {
        "user_id": 1,
        "feature_concept_id": "diagnosis:ms",
        "value": "multiple_sclerosis",
        "unit": None,
        "observed_at": "2026-01-01T00:00:00Z",
        "source_record_type": "user_conditions",
        "source_record_id": 42,
        "verification_state": "UNKNOWN",
        "confidence": None,
    }
    assert validate_feature_index_row(row)["source_record_id"] == 42
    bad = dict(row)
    bad["source_record_id"] = None
    with pytest.raises(Know06ContractError, match="LINEAGE_REQUIRED"):
        validate_feature_index_row(bad)
    llm = dict(row)
    llm["source_record_type"] = "llm"
    with pytest.raises(Know06ContractError):
        validate_feature_index_row(llm)
    reject_llm_invented_user_fact(source="manual")  # allowed path no-op
    with pytest.raises(Know06ContractError, match="LLM_INVENTED"):
        reject_llm_invented_user_fact(source="llm")


def test_applicability_input_vocabulary_and_missing_features():
    assert "diagnosis" in APPLICABILITY_INPUT_FEATURES
    assert "disease_duration" in APPLICABILITY_INPUT_FEATURES
    out = validate_applicability_rules(
        {
            "required_features": ["diagnosis", "age"],
            "optional_features": ["phenotype"],
            "present_features": ["diagnosis"],
        }
    )
    assert out["missing_required_features"] == ["age"]
    assert out["overall_applicability"] == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(Know06ContractError, match="UNKNOWN_APPLICABILITY_FEATURE"):
        validate_applicability_rules(
            {"required_features": ["favorite_color"], "optional_features": [], "present_features": []}
        )


def _base_match(**overrides):
    payload = {
        "population_match": "PARTIAL",
        "disease_match": "YES",
        "phenotype_match": "UNKNOWN",
        "biomarker_match": "UNKNOWN",
        "treatment_context_match": "UNKNOWN",
        "evidence_strength": "MODERATE",
        "directness": "INDIRECT",
        "freshness": "CURRENT",
        "contraindication_status": "ABSENT",
        "medical_safety_state": "SAFE_CONTEXT",
        "missing_required_features": [],
        "overall_applicability": "EVIDENCE_MAY_BE_RELEVANT",
        "transparent_match_explanation": "disease token matched; phenotype unknown",
        "evidence_ku_id": "ku:168",
        "feature_lineage_refs": [{"source_record_type": "user_conditions", "source_record_id": 7}],
    }
    payload.update(overrides)
    return payload


def test_user_evidence_match_shape_and_lineage():
    out = validate_user_evidence_match(_base_match())
    assert set(USER_EVIDENCE_MATCH_FIELDS).issubset(out.keys())
    assert out["evidence_ku_id"] == "ku:168"
    with pytest.raises(Know06ContractError, match="MATCH_LINEAGE_REQUIRED"):
        validate_user_evidence_match(_base_match(evidence_ku_id=""))


def test_safe_states_accepted_forbidden_rejected_including_synonyms():
    for state in SAFE_APPLICABILITY_STATES:
        assert validate_safe_applicability_state(state) == state
    for state in FORBIDDEN_APPLICABILITY_STATES:
        assert is_forbidden_applicability_state(state)
        with pytest.raises(Know06ContractError, match="FORBIDDEN"):
            validate_safe_applicability_state(state)
    for syn in ("CURE", "take-this-drug", "STOP_MEDICATION", "FOUND_TREATMENT"):
        assert is_forbidden_applicability_state(syn)
        with pytest.raises(Know06ContractError):
            validate_safe_applicability_state(syn)


def test_contraindication_fail_closed():
    with pytest.raises(Know06ContractError, match="CONTRAINDICATION_FAIL_CLOSED"):
        validate_user_evidence_match(
            _base_match(
                contraindication_status="PRESENT",
                overall_applicability="EVIDENCE_SUPPORTED_OPTION",
            )
        )
    ok = validate_user_evidence_match(
        _base_match(
            contraindication_status="PRESENT",
            overall_applicability="POTENTIAL_CONTRAINDICATION",
            medical_safety_state="FAIL_CLOSED",
        )
    )
    assert ok["overall_applicability"] == "POTENTIAL_CONTRAINDICATION"


def test_conflicting_and_insufficient_evidence():
    conflict = validate_user_evidence_match(_base_match(overall_applicability="CONFLICTING_EVIDENCE"))
    assert conflict["overall_applicability"] == "CONFLICTING_EVIDENCE"
    insuff = build_insufficient_match(
        evidence_ku_id="ku:1",
        feature_lineage_refs=[{"source_record_type": "user_profile_core", "source_record_id": 1}],
        missing_required_features=["genotype"],
        explanation="required genotype absent",
    )
    assert insuff["overall_applicability"] == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(Know06ContractError, match="MISSING_FEATURES_BLOCK_STRONG_MATCH"):
        validate_user_evidence_match(
            _base_match(
                missing_required_features=["biomarker"],
                overall_applicability="GUIDELINE_ALIGNED_OPTION",
            )
        )


def test_i5_cannot_write_personal_memory_or_own_decision():
    with pytest.raises(Know06ContractError, match="I5_PERSONAL_MEMORY_WRITE_DENIED"):
        reject_i5_personal_memory_write(operation="insert_user_memory_facts")
    with pytest.raises(Know06ContractError, match="I5_USER_PROFILE_MUTATION_DENIED"):
        reject_i5_user_profile_mutation(operation="update_user_profile_core")
    # Static ownership proof: know06 package must not import write helpers for personal SoTs.
    know06_dir = ROOT / "backend/app/services/i5/know06"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in know06_dir.glob("*.py"))
    for banned in (
        "session.add(",
        "UserMemoryFact(",
        "UserCondition(",
        "UserProfileCore(",
        "db.commit(",
    ):
        assert banned not in blob


def test_cross_layer_matrix_covers_required_items():
    items = {r.contract_item for r in CROSS_LAYER_MATRIX}
    assert {
        "clinical_feature_projection",
        "lineage",
        "consent_privacy_boundary",
        "longitudinal_context",
        "evidence_matching",
        "contraindication_context",
        "safe_applicability_state",
        "recommendation_plan_consumption",
        "notification_handoff_boundary",
    }.issubset(items)
    assert RUNTIME_INTEGRATION_GAPS
    assert all(r.i5_provides for r in CROSS_LAYER_MATRIX)


def test_authority_docs_paths_exist():
    for rel in AUTHORITY_DOCS:
        assert (ROOT / rel).is_file()


def test_d01_d19_coverage_manifest_still_uncovered_none():
    """Regression: coverage manifest authority remains present (no domain matrix falsify)."""
    manifest = (ROOT / "backend/config/i5/coverage_manifest_v1.yaml").read_text(encoding="utf-8")
    assert "D01" in manifest and "D19" in manifest


def test_autonomous_weekly_side_stage_default_on_regression():
    from backend.app.services.i5.governed_weekly_runtime import (
        WEEKLY_CRON_DAY_OF_WEEK,
        WEEKLY_CRON_HOUR,
        WEEKLY_CRON_MINUTE,
        WEEKLY_SCHEDULER_TIMEZONE_NAME,
    )

    assert WEEKLY_SCHEDULER_TIMEZONE_NAME == "Asia/Tehran"
    assert WEEKLY_CRON_DAY_OF_WEEK == "fri"
    assert WEEKLY_CRON_HOUR == 3
    assert WEEKLY_CRON_MINUTE == 30


def test_i5_retrieval_module_still_importable_regression():
    from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK

    assert STATUS_OK
