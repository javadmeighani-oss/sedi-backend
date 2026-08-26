"""Deterministic KNOW-06 contract validators (no persistence; no personal writes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from backend.app.services.i5.know06 import (
    APPLICABILITY_INPUT_FEATURES,
    APPLICABILITY_RULE_FIELDS,
    CONTRAINDICATION_FAIL_CLOSED_STATUSES,
    FAIL_CLOSED_OVERALL_STATES,
    FORBIDDEN_APPLICABILITY_STATES,
    FORBIDDEN_STATE_SYNONYMS,
    I5_CANONICAL_USER_RECORD,
    I5_PERSONAL_MEMORY_WRITE,
    I5_RUNTIME_PERSONAL_DECISION_OWNER,
    I5_USER_PROFILE_MUTATION,
    RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5,
    SAFE_APPLICABILITY_STATES,
    USER_CLINICAL_FEATURE_INDEX_FIELDS,
    USER_EVIDENCE_MATCH_FIELDS,
    USER_EVIDENCE_MATCH_LINEAGE_FIELDS,
)
from backend.app.services.i5.know06.sot_lineage import (
    ALLOWED_SOURCE_RECORD_TYPES,
    LLM_INVENTED_USER_FACT_PATH_ALLOWED,
    LINEAGE_REQUIRED,
)


class Know06ContractError(ValueError):
    """Fail-closed KNOW-06 contract violation."""


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def assert_i5_ownership_boundary() -> None:
    if RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5:
        raise Know06ContractError("RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5 must be NO")
    if I5_PERSONAL_MEMORY_WRITE or I5_CANONICAL_USER_RECORD or I5_USER_PROFILE_MUTATION:
        raise Know06ContractError("I5 personal memory / canonical user record / profile mutation forbidden")
    if I5_RUNTIME_PERSONAL_DECISION_OWNER:
        raise Know06ContractError("I5 must not own runtime personal decisioning")
    if LLM_INVENTED_USER_FACT_PATH_ALLOWED:
        raise Know06ContractError("LLM-invented user fact path is forbidden")


def reject_i5_personal_memory_write(*, operation: str) -> None:
    """Any I5 attempt to write personal memory must fail closed."""
    raise Know06ContractError(f"I5_PERSONAL_MEMORY_WRITE_DENIED:{operation}")


def reject_i5_user_profile_mutation(*, operation: str) -> None:
    raise Know06ContractError(f"I5_USER_PROFILE_MUTATION_DENIED:{operation}")


def reject_llm_invented_user_fact(*, source: str) -> None:
    if source in {"llm", "model", "gpt", "inferred_unlined", "hallucinated"}:
        raise Know06ContractError(f"LLM_INVENTED_USER_FACT_FORBIDDEN:{source}")


def is_forbidden_applicability_state(state: str) -> bool:
    token = _norm(state)
    if token in FORBIDDEN_APPLICABILITY_STATES:
        return True
    if token in FORBIDDEN_STATE_SYNONYMS:
        return True
    # Collapse common bypass patterns.
    compact = token.replace("_", "")
    for banned in FORBIDDEN_APPLICABILITY_STATES | FORBIDDEN_STATE_SYNONYMS:
        if banned.replace("_", "") == compact:
            return True
    return False


def validate_safe_applicability_state(state: str) -> str:
    token = _norm(state)
    if is_forbidden_applicability_state(token):
        raise Know06ContractError(f"FORBIDDEN_APPLICABILITY_STATE:{token}")
    if token not in SAFE_APPLICABILITY_STATES:
        raise Know06ContractError(f"UNKNOWN_APPLICABILITY_STATE:{token}")
    return token


def validate_feature_index_row(row: Mapping[str, Any]) -> dict[str, Any]:
    missing = [f for f in USER_CLINICAL_FEATURE_INDEX_FIELDS if f not in row]
    if missing:
        raise Know06ContractError(f"FEATURE_INDEX_MISSING_FIELDS:{missing}")
    if LINEAGE_REQUIRED:
        if not row.get("source_record_type") or row.get("source_record_id") in (None, ""):
            raise Know06ContractError("LINEAGE_REQUIRED")
        src_type = str(row["source_record_type"])
        if src_type not in ALLOWED_SOURCE_RECORD_TYPES:
            raise Know06ContractError(f"UNKNOWN_SOURCE_RECORD_TYPE:{src_type}")
        if src_type == "llm" or str(row.get("source_record_id")).startswith("llm:"):
            raise Know06ContractError("LLM_INVENTED_USER_FACT_FORBIDDEN")
    out = {k: row[k] for k in USER_CLINICAL_FEATURE_INDEX_FIELDS}
    return out


@dataclass(frozen=True)
class ApplicabilityInputContract:
    required_features: tuple[str, ...]
    optional_features: tuple[str, ...] = ()
    present_features: frozenset[str] = field(default_factory=frozenset)

    def missing_required_features(self) -> list[str]:
        return [f for f in self.required_features if f not in self.present_features]

    def overall_when_missing(self) -> str:
        if self.missing_required_features():
            return "INSUFFICIENT_EVIDENCE"
        return "EVIDENCE_MAY_BE_RELEVANT"


def validate_applicability_rules(rules: Mapping[str, Any]) -> dict[str, Any]:
    for key in APPLICABILITY_RULE_FIELDS:
        if key == "missing_required_features":
            continue
        if key not in rules:
            raise Know06ContractError(f"APPLICABILITY_RULE_MISSING:{key}")
    required = tuple(rules["required_features"] or ())
    optional = tuple(rules.get("optional_features") or ())
    for feat in (*required, *optional):
        if feat not in APPLICABILITY_INPUT_FEATURES:
            raise Know06ContractError(f"UNKNOWN_APPLICABILITY_FEATURE:{feat}")
    present = frozenset(rules.get("present_features") or ())
    contract = ApplicabilityInputContract(
        required_features=required,
        optional_features=optional,
        present_features=present,
    )
    missing = contract.missing_required_features()
    return {
        "required_features": list(required),
        "optional_features": list(optional),
        "missing_required_features": missing,
        "overall_applicability": contract.overall_when_missing(),
    }


def validate_user_evidence_match(payload: Mapping[str, Any]) -> dict[str, Any]:
    missing_fields = [f for f in USER_EVIDENCE_MATCH_FIELDS if f not in payload]
    if missing_fields:
        raise Know06ContractError(f"MATCH_MISSING_FIELDS:{missing_fields}")
    for lf in USER_EVIDENCE_MATCH_LINEAGE_FIELDS:
        if not payload.get(lf):
            raise Know06ContractError(f"MATCH_LINEAGE_REQUIRED:{lf}")

    state = validate_safe_applicability_state(str(payload["overall_applicability"]))
    contra = _norm(payload.get("contraindication_status"))
    missing_req = list(payload.get("missing_required_features") or [])

    if contra in CONTRAINDICATION_FAIL_CLOSED_STATUSES:
        if state not in {"POTENTIAL_CONTRAINDICATION", "SPECIALIST_REVIEW_REQUIRED", "NOT_APPLICABLE"}:
            raise Know06ContractError("CONTRAINDICATION_FAIL_CLOSED")

    if missing_req and state not in FAIL_CLOSED_OVERALL_STATES | {"INSUFFICIENT_EVIDENCE"}:
        # Missing required features must not claim guideline/treatment-like support.
        if state in {
            "GUIDELINE_ALIGNED_OPTION",
            "EVIDENCE_SUPPORTED_OPTION",
            "CLINICAL_TRIAL_POTENTIAL_MATCH",
        }:
            raise Know06ContractError("MISSING_FEATURES_BLOCK_STRONG_MATCH")

    if state == "CONFLICTING_EVIDENCE" and _norm(payload.get("evidence_strength")) in {
        "HIGH",
        "STRONG",
    }:
        # Conflicting evidence must not silently upgrade strength semantics.
        pass

    out = {k: payload[k] for k in USER_EVIDENCE_MATCH_FIELDS}
    out["overall_applicability"] = state
    out["evidence_ku_id"] = payload["evidence_ku_id"]
    out["feature_lineage_refs"] = payload["feature_lineage_refs"]
    return out


def build_insufficient_match(
    *,
    evidence_ku_id: str,
    feature_lineage_refs: Sequence[Mapping[str, Any]],
    missing_required_features: Sequence[str],
    explanation: str,
) -> dict[str, Any]:
    return validate_user_evidence_match(
        {
            "population_match": "UNKNOWN",
            "disease_match": "UNKNOWN",
            "phenotype_match": "UNKNOWN",
            "biomarker_match": "UNKNOWN",
            "treatment_context_match": "UNKNOWN",
            "evidence_strength": "UNKNOWN",
            "directness": "UNKNOWN",
            "freshness": "UNKNOWN",
            "contraindication_status": "ABSENT",
            "medical_safety_state": "INSUFFICIENT_CONTEXT",
            "missing_required_features": list(missing_required_features),
            "overall_applicability": "INSUFFICIENT_EVIDENCE",
            "transparent_match_explanation": explanation,
            "evidence_ku_id": evidence_ku_id,
            "feature_lineage_refs": list(feature_lineage_refs),
        }
    )
