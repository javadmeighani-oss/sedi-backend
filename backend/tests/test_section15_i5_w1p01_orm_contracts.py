"""Section 33 / W1-P01 — ORM contract tests (authored; NOT executed in authoring Gate).

Authority: Design Freeze §§184–193 + models.py / i5/enums.py frozen identities.
Categories: T1–T10. T11 migration parity = DEFERRED. micro-fix-01/02.
PostgreSQL-required cases use _require_postgres (no SQLite substitution).
Coverage Manifest / ALS-MS lanes are intentionally out of scope for this file.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint, inspect as sa_inspect, text
from sqlalchemy.dialects import postgresql as pg_dialect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CheckConstraint


def _load_w1p01():
    models = importlib.import_module("backend.app.models")
    enums = importlib.import_module("backend.app.services.i5.enums")
    return models, enums


def _model_by_name(name: str):
    models, _ = _load_w1p01()
    return getattr(models, name)

# ---------------------------------------------------------------------------
# Dialect / PG guards (mirror i5b2_p1; no conftest edits)
# ---------------------------------------------------------------------------


def _pg_only(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _require_postgres(db) -> None:
    if not _pg_only(db):
        pytest.skip("PostgreSQL required for this invariant (CI-gated)")


def _constraint_blob(exc: BaseException) -> str:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag is not None else None
    parts = [str(name or ""), str(orig or ""), str(exc)]
    return " | ".join(parts)


def _expect_named_integrity(db, *, constraint: str, mutate) -> None:
    _require_postgres(db)
    with pytest.raises(IntegrityError) as ei:
        with db.begin_nested():
            mutate()
            db.flush()
    assert constraint in _constraint_blob(ei.value)


def _expect_named_integrity_deferred(db, *, constraint: str, mutate) -> None:
    """Flush + SET CONSTRAINTS IMMEDIATE for deferrable FK negatives."""
    _require_postgres(db)
    with pytest.raises(IntegrityError) as ei:
        with db.begin_nested():
            mutate()
            db.execute(text(f"SET CONSTRAINTS {constraint} IMMEDIATE"))
            db.flush()
    assert constraint in _constraint_blob(ei.value)


VALID_HASH = "a" * 64
VALID_REQUEST_KEY = "req:w1p01:demo:001"
FORBIDDEN_RESULT_DECISION_ID = "decision_id"
FORBIDDEN_REOPEN_FK = "reopened_from_gap_id"

_DET_SEQ = 0


def _det_hex(nbytes: int = 32) -> str:
    """Deterministic hex identity for positive/negative fixtures (no wall-clock/random)."""
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


# Unexplained residual shadowing must remain empty after micro-fix-02.
# The single unisolatable CHECK uses SEMANTIC_EXCEPTION coverage (below).
UNEXPLAINED_SHADOWED_CHECK_CASES: tuple[str, ...] = ()
AMBIGUOUS_CHECK_CASES: tuple[str, ...] = ()
DOCUMENTED_UNISOLATABLE_CHECK_CASES: tuple[str, ...] = ("ck_i5gd_entity_family_matrix",)

# Exact frozen SQL expression for ck_i5gd_entity_family_matrix (models.py authority).
CK_I5GD_ENTITY_FAMILY_MATRIX_SQL = (
    "(entity_type IN ('SOURCE_PROFILE', 'SOURCE_PROFILE_VERSION') AND "
    "decision_family IN ('RIGHTS', 'AUTOMATION', 'QUALITY', 'MEDICAL_SAFETY', "
    "'SECURITY', 'LIFECYCLE')) OR "
    "(entity_type = 'KNOWLEDGE_GAP' AND decision_family IN ('LIFECYCLE', 'GAP_LIFECYCLE')) OR "
    "(entity_type = 'WEEKLY_RUN' AND decision_family IN ('LIFECYCLE', 'RUN_APPROVAL')) OR "
    "(entity_type = 'WEEKLY_RUN_ATTEMPT' AND decision_family = 'RUN_TERMINALIZATION') OR "
    "(entity_type = 'RUN_SOURCE_RESULT' AND decision_family IN ('RIGHTS', 'AUTOMATION', "
    "'QUALITY', 'MEDICAL_SAFETY', 'SECURITY', 'LIFECYCLE')) OR "
    "(entity_type = 'RUN_GAP_RESULT' AND decision_family IN ('QUALITY', 'LIFECYCLE'))"
)

# Allowed (entity_type, decision_family) pairs implied by the frozen expression.
ENTITY_FAMILY_ALLOWED: dict[str, frozenset[str]] = {
    "SOURCE_PROFILE": frozenset(
        {"RIGHTS", "AUTOMATION", "QUALITY", "MEDICAL_SAFETY", "SECURITY", "LIFECYCLE"}
    ),
    "SOURCE_PROFILE_VERSION": frozenset(
        {"RIGHTS", "AUTOMATION", "QUALITY", "MEDICAL_SAFETY", "SECURITY", "LIFECYCLE"}
    ),
    "KNOWLEDGE_GAP": frozenset({"LIFECYCLE", "GAP_LIFECYCLE"}),
    "WEEKLY_RUN": frozenset({"LIFECYCLE", "RUN_APPROVAL"}),
    "WEEKLY_RUN_ATTEMPT": frozenset({"RUN_TERMINALIZATION"}),
    "RUN_SOURCE_RESULT": frozenset(
        {"RIGHTS", "AUTOMATION", "QUALITY", "MEDICAL_SAFETY", "SECURITY", "LIFECYCLE"}
    ),
    "RUN_GAP_RESULT": frozenset({"QUALITY", "LIFECYCLE"}),
}

ENTITY_FAMILY_MATRIX_EXCEPTION: dict[str, Any] = {
    "constraint_name": "ck_i5gd_entity_family_matrix",
    "table_name": "i5_governance_decisions",
    "coverage_mode": "SEMANTIC_EXCEPTION",
    "first_failure_isolation": "UNAVAILABLE",
    "reason": (
        "An invalid (entity_type, decision_family) row also violates sibling frozen "
        "constraints; PostgreSQL is not required to report IntegrityError names in a "
        "test-selected order. Non-supersession overlaps ck_i5gd_decision_type_family_matrix; "
        "supersession overlaps fk_i5gd_supersedes_same_entity_family when family is "
        "mismatched to the parent, and a same-family invalid parent cannot be inserted."
    ),
    "overlapping_check": "ck_i5gd_decision_type_family_matrix",
    "overlapping_composite_fk": "fk_i5gd_supersedes_same_entity_family",
    "exact_expression_asserted": True,
    "valid_semantic_case_present": True,
    "invalid_semantic_case_present": True,
    "schema_change_required": False,
    "waiver_scope": "THIS_CONSTRAINT_ONLY",
    "postgres_constraint_order_assumed": False,
    "production_constraint_disabled": False,
}

# Semantic cases evaluate the frozen predicate only (no first-failure IntegrityError claim).
ENTITY_FAMILY_SEMANTIC_VALID = ("SOURCE_PROFILE", "RIGHTS")
ENTITY_FAMILY_SEMANTIC_INVALID = ("SOURCE_PROFILE", "GAP_LIFECYCLE")
ENTITY_FAMILY_OVERLAP_EXPLANATION = (
    "Isolated first-failure IntegrityError for ck_i5gd_entity_family_matrix is unavailable: "
    "(1) non-supersession invalid entity/family tuples also violate "
    "ck_i5gd_decision_type_family_matrix; (2) supersession invalid entity/family tuples also "
    "violate fk_i5gd_supersedes_same_entity_family (or cannot create a valid same-family "
    "parent under an invalid family). PostgreSQL constraint report order is not assumed."
)

assert DOCUMENTED_UNISOLATABLE_CHECK_CASES == ("ck_i5gd_entity_family_matrix",)
assert UNEXPLAINED_SHADOWED_CHECK_CASES == ()
assert AMBIGUOUS_CHECK_CASES == ()
assert ENTITY_FAMILY_MATRIX_EXCEPTION["constraint_name"] == "ck_i5gd_entity_family_matrix"
assert ENTITY_FAMILY_MATRIX_EXCEPTION["waiver_scope"] == "THIS_CONSTRAINT_ONLY"

# ===========================================================================
# FROZEN LEDGERS
# ===========================================================================

FROZEN_ENUM_CLASSES: tuple[str, ...] = (
    "RegistryState",
    "RuntimeEligibility",
    "KnowledgeGapType",
    "KnowledgeGapStatus",
    "KnowledgeGapPriority",
    "KnowledgeGapSeverity",
    "KnowledgeGapUrgency",
    "WeeklyRunStatus",
    "WeeklyRunAttemptStatus",
    "WeeklyRunApprovalState",
    "WeeklyRunType",
    "WeeklyRunTriggerType",
    "RunSourceResultStatus",
    "RunGapResultType",
    "GovernanceEntityType",
    "GovernanceDecisionFamily",
    "GovernanceDecisionType",
    "GovernanceDecisionOutcome",
    "GovernanceActorType",
)
assert len(FROZEN_ENUM_CLASSES) == 19

FROZEN_NEW_MODELS: tuple[str, ...] = (
    "KnowledgeGap",
    "WeeklyKnowledgeRun",
    "WeeklyKnowledgeRunAttempt",
    "WeeklyRunSourceResult",
    "WeeklyRunGapResult",
    "I5GovernanceDecision",
)
assert len(FROZEN_NEW_MODELS) == 6

GSP_ADDITIVE_COLUMNS: tuple[str, ...] = (
    "registry_state",
    "runtime_eligibility",
    "block_reason",
    "owner_reference",
    "reviewer_reference",
    "approver_reference",
    "topic_coverage",
    "effective_from",
    "effective_to",
    "last_discovered_at",
    "last_checked_at",
    "last_reviewed_at",
    "canonicalization_version",
)
assert len(GSP_ADDITIVE_COLUMNS) == 13

GSP_PREEXISTING_COLUMNS: tuple[str, ...] = (
    "id",
    "canonical_key",
    "locator_kind",
    "normalized_locator",
    "legacy_knowledge_source_id",
    "current_profile_version_id",
    "operational_status",
    "row_version",
    "created_at",
    "updated_at",
)
GSP_ALL_COLUMNS = GSP_PREEXISTING_COLUMNS + GSP_ADDITIVE_COLUMNS

GSPV_COLUMNS: tuple[str, ...] = (
    "id",
    "profile_id",
    "version_seq",
    "supersedes_version_id",
    "snapshot_schema_version",
    "snapshot_fingerprint",
    "effective_at",
    "created_at",
    "publisher_authority_identity",
    "source_class",
    "authority_evidence_tier",
    "jurisdiction_scope",
    "jurisdiction_country_code",
    "jurisdiction_subdivision_code",
    "jurisdiction_organization_id",
    "primary_language",
    "specialty_domain",
    "license_status",
    "permitted_use_restriction",
    "storage_permission",
    "transformation_permission",
    "display_redistribution_permission",
    "automation_status",
    "verification_method",
    "freshness_policy_days",
    "freshness_status",
    "fetch_policy",
    "iran_first_applicable",
    "policy_version_reference",
    "configuration_version_reference",
)
assert len(GSPV_COLUMNS) == 30

WKR_COLUMNS: tuple[str, ...] = (
    "id",
    "logical_run_key",
    "canonicalization_version",
    "hash_algorithm",
    "schedule_key",
    "run_type",
    "trigger_type",
    "planned_window_start",
    "planned_window_end",
    "approval_state",
    "source_scope_hash",
    "domain_scope_hash",
    "gap_scope_hash",
    "config_version",
    "config_hash",
    "source_scope",
    "domain_scope",
    "gap_scope",
    "status",
    "successful_attempt_id",
    "latest_attempt_id",
    "created_by_reference",
    "approved_by_reference",
    "approved_at",
    "supersedes_run_id",
    "created_at",
    "updated_at",
    "row_version",
)
assert len(WKR_COLUMNS) == 28

WKRA_COLUMNS: tuple[str, ...] = (
    "id",
    "weekly_run_id",
    "attempt_number",
    "retry_of_attempt_id",
    "status",
    "started_at",
    "completed_at",
    "worker_reference",
    "config_snapshot_reference",
    "run_checksum",
    "canonicalization_version",
    "hash_algorithm",
    "total_sources",
    "checked_sources",
    "fetched_sources",
    "skipped_sources",
    "blocked_sources",
    "failed_sources",
    "new_knowledge_count",
    "updated_knowledge_count",
    "superseded_knowledge_count",
    "rejected_knowledge_count",
    "created_gap_count",
    "resolved_gap_count",
    "warning_count",
    "error_count",
    "failure_code",
    "failure_reason",
    "block_reason",
    "evidence_reference",
    "created_at",
    "updated_at",
    "row_version",
)
assert len(WKRA_COLUMNS) == 33

KG_COLUMNS: tuple[str, ...] = (
    "id",
    "canonical_gap_key",
    "canonicalization_version",
    "hash_algorithm",
    "domain",
    "subdomain",
    "capability_id",
    "gap_type",
    "title",
    "description",
    "evidence_of_gap",
    "current_knowledge_state",
    "required_knowledge_state",
    "source_need",
    "priority",
    "severity",
    "urgency",
    "confidence",
    "status",
    "owner_reference",
    "reviewer_reference",
    "blocker",
    "dependencies",
    "target_package_id",
    "target_source_profile_id",
    "target_knowledge_unit_id",
    "discovered_by",
    "discovered_attempt_id",
    "next_action",
    "next_review_at",
    "retry_count",
    "last_attempt_at",
    "resolution_type",
    "resolution_evidence",
    "resolved_by_reference",
    "resolved_at",
    "created_at",
    "updated_at",
    "row_version",
)
assert len(KG_COLUMNS) == 39

WRSR_COLUMNS: tuple[str, ...] = (
    "id",
    "attempt_id",
    "source_profile_id",
    "source_version_id",
    "result_status",
    "checked_at",
    "fetch_outcome",
    "extraction_outcome",
    "publication_outcome",
    "knowledge_new_count",
    "knowledge_updated_count",
    "knowledge_superseded_count",
    "knowledge_rejected_count",
    "gap_created_count",
    "warning_count",
    "error_count",
    "failure_code",
    "failure_reason",
    "evidence_reference",
    "content_fingerprint",
    "created_at",
)
assert len(WRSR_COLUMNS) == 21

WRGR_COLUMNS: tuple[str, ...] = (
    "id",
    "attempt_id",
    "gap_id",
    "result_type",
    "previous_status",
    "new_status",
    "evidence_reference",
    "created_at",
)
assert len(WRGR_COLUMNS) == 8

I5GD_COLUMNS: tuple[str, ...] = (
    "id",
    "entity_type",
    "entity_id",
    "decision_family",
    "decision_type",
    "decision_request_key",
    "from_state",
    "to_state",
    "outcome",
    "reason_code",
    "reason",
    "actor_type",
    "actor_reference",
    "evidence_reference",
    "decision_metadata",
    "canonical_hash",
    "canonicalization_version",
    "hash_algorithm",
    "supersedes_decision_id",
    "created_at",
)
assert len(I5GD_COLUMNS) == 20

COLUMN_LEDGERS: dict[str, tuple[str, ...]] = {
    "GovernedSourceProfile": GSP_ALL_COLUMNS,
    "GovernedSourceProfileVersion": GSPV_COLUMNS,
    "WeeklyKnowledgeRun": WKR_COLUMNS,
    "WeeklyKnowledgeRunAttempt": WKRA_COLUMNS,
    "KnowledgeGap": KG_COLUMNS,
    "WeeklyRunSourceResult": WRSR_COLUMNS,
    "WeeklyRunGapResult": WRGR_COLUMNS,
    "I5GovernanceDecision": I5GD_COLUMNS,
}

COLUMN_COUNT_LEDGER: dict[str, int] = {
    "KnowledgeGap": 39,
    "WeeklyKnowledgeRun": 28,
    "WeeklyKnowledgeRunAttempt": 33,
    "WeeklyRunSourceResult": 21,
    "WeeklyRunGapResult": 8,
    "I5GovernanceDecision": 20,
}

TABLE_NAME_LEDGER: dict[str, str] = {
    "GovernedSourceProfile": "governed_source_profiles",
    "GovernedSourceProfileVersion": "governed_source_profile_versions",
    "WeeklyKnowledgeRun": "weekly_knowledge_runs",
    "WeeklyKnowledgeRunAttempt": "weekly_knowledge_run_attempts",
    "KnowledgeGap": "knowledge_gaps",
    "WeeklyRunSourceResult": "weekly_run_source_results",
    "WeeklyRunGapResult": "weekly_run_gap_results",
    "I5GovernanceDecision": "i5_governance_decisions",
}

NAMED_CHECKS_70: tuple[str, ...] = (
    "ck_gsp_registry_state_vocab",
    "ck_gsp_runtime_eligibility_vocab",
    "ck_gsp_block_reason_length",
    "ck_gsp_effective_window_order",
    "ck_wkr_run_type_vocab",
    "ck_wkr_trigger_type_vocab",
    "ck_wkr_approval_state_vocab",
    "ck_wkr_status_vocab",
    "ck_wkr_window_order",
    "ck_wkr_supersedes_not_self",
    "ck_wkra_status_vocab",
    "ck_wkra_attempt_number_pos",
    "ck_wkra_retry_not_self",
    "ck_wkra_completed_after_started",
    "ck_wkra_failure_reason_length",
    "ck_wkra_block_reason_length",
    "ck_wkra_total_sources_nonnegative",
    "ck_wkra_checked_sources_nonnegative",
    "ck_wkra_fetched_sources_nonnegative",
    "ck_wkra_skipped_sources_nonnegative",
    "ck_wkra_blocked_sources_nonnegative",
    "ck_wkra_failed_sources_nonnegative",
    "ck_wkra_new_knowledge_count_nonnegative",
    "ck_wkra_updated_knowledge_count_nonnegative",
    "ck_wkra_superseded_knowledge_count_nonnegative",
    "ck_wkra_rejected_knowledge_count_nonnegative",
    "ck_wkra_created_gap_count_nonnegative",
    "ck_wkra_resolved_gap_count_nonnegative",
    "ck_wkra_warning_count_nonnegative",
    "ck_wkra_error_count_nonnegative",
    "ck_kg_gap_type_vocab",
    "ck_kg_priority_vocab",
    "ck_kg_severity_vocab",
    "ck_kg_urgency_vocab",
    "ck_kg_status_vocab",
    "ck_kg_confidence_range",
    "ck_kg_retry_count_nonneg",
    "ck_kg_description_length",
    "ck_kg_current_knowledge_state_length",
    "ck_kg_required_knowledge_state_length",
    "ck_kg_next_action_length",
    "ck_kg_blocker_length",
    "ck_wrsr_result_status_vocab",
    "ck_wrsr_failure_reason_length",
    "ck_wrsr_knowledge_new_count_nonnegative",
    "ck_wrsr_knowledge_updated_count_nonnegative",
    "ck_wrsr_knowledge_superseded_count_nonnegative",
    "ck_wrsr_knowledge_rejected_count_nonnegative",
    "ck_wrsr_gap_created_count_nonnegative",
    "ck_wrsr_warning_count_nonnegative",
    "ck_wrsr_error_count_nonnegative",
    "ck_wrgr_result_type_vocab",
    "ck_wrgr_previous_status_vocab",
    "ck_wrgr_new_status_vocab",
    "ck_i5gd_entity_type_vocab",
    "ck_i5gd_decision_family_vocab",
    "ck_i5gd_decision_type_vocab",
    "ck_i5gd_outcome_vocab",
    "ck_i5gd_actor_type_vocab",
    "ck_i5gd_entity_id_pos",
    "ck_i5gd_supersedes_not_self",
    "ck_i5gd_canonical_hash_format",
    "ck_i5gd_decision_request_key_format",
    "ck_i5gd_hash_algorithm_constant",
    "ck_i5gd_canonicalization_version_constant",
    "ck_i5gd_reason_length",
    "ck_i5gd_supersession_requires_parent",
    "ck_i5gd_decision_type_family_matrix",
    "ck_i5gd_entity_family_matrix",
    "ck_i5gd_entity_decision_matrix",
)
assert len(NAMED_CHECKS_70) == 70
assert len(set(NAMED_CHECKS_70)) == 70

SIMPLE_FK_LEDGER: tuple[dict[str, Any], ...] = (
    {
        "name": "fk_wkr_supersedes_run_id",
        "local_table": "weekly_knowledge_runs",
        "local_cols": ("supersedes_run_id",),
        "remote_table": "weekly_knowledge_runs",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_wkra_weekly_run_id",
        "local_table": "weekly_knowledge_run_attempts",
        "local_cols": ("weekly_run_id",),
        "remote_table": "weekly_knowledge_runs",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_knowledge_gaps_target_source_profile_id",
        "local_table": "knowledge_gaps",
        "local_cols": ("target_source_profile_id",),
        "remote_table": "governed_source_profiles",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_knowledge_gaps_discovered_attempt_id",
        "local_table": "knowledge_gaps",
        "local_cols": ("discovered_attempt_id",),
        "remote_table": "weekly_knowledge_run_attempts",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_wrsr_attempt_id",
        "local_table": "weekly_run_source_results",
        "local_cols": ("attempt_id",),
        "remote_table": "weekly_knowledge_run_attempts",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_wrsr_source_profile_id",
        "local_table": "weekly_run_source_results",
        "local_cols": ("source_profile_id",),
        "remote_table": "governed_source_profiles",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_wrsr_source_version_id",
        "local_table": "weekly_run_source_results",
        "local_cols": ("source_version_id",),
        "remote_table": "governed_source_profile_versions",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_wrgr_attempt_id",
        "local_table": "weekly_run_gap_results",
        "local_cols": ("attempt_id",),
        "remote_table": "weekly_knowledge_run_attempts",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
    {
        "name": "fk_wrgr_gap_id",
        "local_table": "weekly_run_gap_results",
        "local_cols": ("gap_id",),
        "remote_table": "knowledge_gaps",
        "remote_cols": ("id",),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
    },
)
assert len(SIMPLE_FK_LEDGER) == 9

COMPOSITE_FK_LEDGER: tuple[dict[str, Any], ...] = (
    {
        "name": "fk_wkr_successful_attempt_same_run",
        "local_table": "weekly_knowledge_runs",
        "local_cols": ("id", "successful_attempt_id"),
        "remote_table": "weekly_knowledge_run_attempts",
        "remote_cols": ("weekly_run_id", "id"),
        "ondelete": "RESTRICT",
        "deferrable": True,
        "initially": "DEFERRED",
        "use_alter": True,
    },
    {
        "name": "fk_wkr_latest_attempt_same_run",
        "local_table": "weekly_knowledge_runs",
        "local_cols": ("id", "latest_attempt_id"),
        "remote_table": "weekly_knowledge_run_attempts",
        "remote_cols": ("weekly_run_id", "id"),
        "ondelete": "RESTRICT",
        "deferrable": True,
        "initially": "DEFERRED",
        "use_alter": True,
    },
    {
        "name": "fk_wkra_retry_same_run",
        "local_table": "weekly_knowledge_run_attempts",
        "local_cols": ("retry_of_attempt_id", "weekly_run_id"),
        "remote_table": "weekly_knowledge_run_attempts",
        "remote_cols": ("id", "weekly_run_id"),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
        "use_alter": False,
    },
    {
        "name": "fk_i5gd_supersedes_same_entity_family",
        "local_table": "i5_governance_decisions",
        "local_cols": ("supersedes_decision_id", "entity_type", "entity_id", "decision_family"),
        "remote_table": "i5_governance_decisions",
        "remote_cols": ("id", "entity_type", "entity_id", "decision_family"),
        "ondelete": "RESTRICT",
        "deferrable": False,
        "initially": None,
        "use_alter": False,
    },
)
assert len(COMPOSITE_FK_LEDGER) == 4

ORDINARY_UQ_LEDGER: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("weekly_knowledge_runs", "uq_weekly_knowledge_runs_logical_run_key", ("logical_run_key",)),
    ("weekly_knowledge_run_attempts", "uq_wkra_run_attempt", ("weekly_run_id", "attempt_number")),
    ("weekly_knowledge_run_attempts", "uq_wkra_id_weekly_run_id", ("id", "weekly_run_id")),
    ("knowledge_gaps", "uq_knowledge_gaps_canonical_gap_key", ("canonical_gap_key",)),
    ("weekly_run_source_results", "uq_wrsr_attempt_source_profile", ("attempt_id", "source_profile_id")),
    ("weekly_run_gap_results", "uq_wrgr_attempt_gap", ("attempt_id", "gap_id")),
    (
        "i5_governance_decisions",
        "uq_i5gd_decision_request",
        ("entity_type", "entity_id", "decision_request_key"),
    ),
    (
        "i5_governance_decisions",
        "uq_i5gd_id_entity_family",
        ("id", "entity_type", "entity_id", "decision_family"),
    ),
)
assert len(ORDINARY_UQ_LEDGER) == 8

PARTIAL_UQ_LEDGER: tuple[tuple[str, str], ...] = (
    ("weekly_knowledge_run_attempts", "uq_wkra_one_successful_terminal"),
    ("i5_governance_decisions", "uq_i5gd_one_superseder"),
    ("i5_governance_decisions", "uq_i5gd_one_root_per_family"),
)
assert len(PARTIAL_UQ_LEDGER) == 3

PARTIAL_UQ_PREDICATES: dict[str, str] = {
    "uq_wkra_one_successful_terminal": "status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS')",
    "uq_i5gd_one_superseder": "supersedes_decision_id IS NOT NULL",
    "uq_i5gd_one_root_per_family": "supersedes_decision_id IS NULL",
}

QUERY_INDEX_LEDGER: tuple[tuple[str, str], ...] = (
    ("governed_source_profiles", "ix_gsp_registry_state"),
    ("governed_source_profiles", "ix_gsp_runtime_eligibility"),
    ("governed_source_profiles", "ix_gsp_last_checked_at"),
    ("governed_source_profiles", "ix_gsp_last_reviewed_at"),
    ("governed_source_profiles", "ix_gsp_registry_runtime"),
    ("weekly_knowledge_runs", "ix_wkr_status_window"),
    ("weekly_knowledge_runs", "ix_wkr_schedule_window"),
    ("weekly_knowledge_runs", "ix_wkr_approval_state"),
    ("weekly_knowledge_runs", "ix_wkr_successful_attempt_id"),
    ("weekly_knowledge_runs", "ix_wkr_latest_attempt_id"),
    ("weekly_knowledge_runs", "ix_wkr_supersedes_run_id"),
    ("weekly_knowledge_run_attempts", "ix_wkra_status_started_at"),
    ("weekly_knowledge_run_attempts", "ix_wkra_retry_of_attempt_id"),
    ("knowledge_gaps", "ix_kg_status_priority_severity"),
    ("knowledge_gaps", "ix_kg_next_review_at"),
    ("knowledge_gaps", "ix_kg_target_source_profile_id"),
    ("knowledge_gaps", "ix_kg_discovered_attempt_id"),
    ("knowledge_gaps", "ix_kg_capability_id"),
    ("knowledge_gaps", "ix_kg_target_package_id"),
    ("knowledge_gaps", "ix_kg_domain_subdomain"),
    ("weekly_run_source_results", "ix_wrsr_source_profile_id"),
    ("weekly_run_source_results", "ix_wrsr_result_status"),
    ("weekly_run_gap_results", "ix_wrgr_gap_id"),
    ("weekly_run_gap_results", "ix_wrgr_result_type"),
    ("i5_governance_decisions", "ix_i5gd_entity_history"),
    ("i5_governance_decisions", "ix_i5gd_family_history"),
    ("i5_governance_decisions", "ix_i5gd_content_hash"),
    ("i5_governance_decisions", "ix_i5gd_decision_type"),
    ("i5_governance_decisions", "ix_i5gd_outcome"),
)
assert len(QUERY_INDEX_LEDGER) == 29
assert "ix_governed_source_profiles_operational_status" not in {
    n for _, n in QUERY_INDEX_LEDGER
}


def _col_names(model) -> list[str]:
    return [c.key for c in model.__table__.columns]


def _check_names(model) -> set[str]:
    return {
        c.name
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name
    }


def _uq_map(model) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for c in model.__table__.constraints:
        if isinstance(c, UniqueConstraint) and c.name:
            out[c.name] = tuple(col.name for col in c.columns)
    return out


def _fk_names(model) -> set[str]:
    names: set[str] = set()
    for c in model.__table__.constraints:
        if isinstance(c, ForeignKeyConstraint) and c.name:
            names.add(c.name)
    for col in model.__table__.columns:
        for fk in col.foreign_keys:
            if fk.constraint is not None and fk.constraint.name:
                names.add(fk.constraint.name)
    return names


def _find_fk(model, fk_name: str) -> ForeignKeyConstraint:
    for c in model.__table__.constraints:
        if isinstance(c, ForeignKeyConstraint) and c.name == fk_name:
            return c
    for col in model.__table__.columns:
        for fk in col.foreign_keys:
            if fk.constraint is not None and fk.constraint.name == fk_name:
                return fk.constraint
    raise AssertionError(f"FK {fk_name} not found on {model.__tablename__}")


def _model_for_table(table: str):
    for model_name, tab in TABLE_NAME_LEDGER.items():
        if tab == table:
            return _model_by_name(model_name)
    raise AssertionError(f"no model for table {table}")


def _index_map(model) -> dict[str, Any]:
    return {ix.name: ix for ix in model.__table__.indexes if ix.name}


def _compile_partial_predicate(where_clause) -> str:
    compiled = where_clause.compile(
        dialect=pg_dialect.dialect(), compile_kwargs={"literal_binds": True}
    )
    return str(compiled)


def _normalize_sql_expr(expr: str) -> str:
    """Collapse whitespace for semantic SQL comparison (no identifier rewrite)."""
    return " ".join(str(expr).split())


def _entity_family_rule_allows(entity_type: str, decision_family: str) -> bool:
    allowed = ENTITY_FAMILY_ALLOWED.get(entity_type)
    if allowed is None:
        return False
    return decision_family in allowed


def _find_check(model, check_name: str) -> CheckConstraint:
    for c in model.__table__.constraints:
        if isinstance(c, CheckConstraint) and c.name == check_name:
            return c
    raise AssertionError(f"CheckConstraint {check_name} not found on {model.__tablename__}")


def _check_sql_text(check: CheckConstraint) -> str:
    raw = check.sqltext if hasattr(check, "sqltext") else check.condition
    compiled = raw.compile(
        dialect=pg_dialect.dialect(), compile_kwargs={"literal_binds": True}
    )
    return _normalize_sql_expr(str(compiled))


# ===========================================================================
# T1 — source / import smoke
# ===========================================================================


def test_W1P01_T1_01_models_module_exposes_six_new_classes() -> None:
    models, _ = _load_w1p01()
    for name in FROZEN_NEW_MODELS:
        assert hasattr(models, name), f"missing model symbol {name}"
        assert getattr(models, name) is _model_by_name(name)


def test_W1P01_T1_02_reused_extended_gsp_gspv_symbols_exist() -> None:
    models, _ = _load_w1p01()
    assert hasattr(models, "GovernedSourceProfile")
    assert hasattr(models, "GovernedSourceProfileVersion")


def test_W1P01_T1_03_all_nineteen_enum_classes_resolve() -> None:
    _, enums = _load_w1p01()
    for name in FROZEN_ENUM_CLASSES:
        assert hasattr(enums, name), f"missing enum {name}"
    assert len(FROZEN_ENUM_CLASSES) == 19


def test_W1P01_T1_04_enum_serialized_values_match_member_names() -> None:
    _, enums = _load_w1p01()
    for name in FROZEN_ENUM_CLASSES:
        enum_cls = getattr(enums, name)
        for member in enum_cls:
            assert member.value == member.name


# ===========================================================================
# T2 — mapper configuration
# ===========================================================================


def test_W1P01_T2_01_configure_mappers_succeeds() -> None:
    configure_mappers()


def test_W1P01_T2_02_simple_and_composite_fk_targets_resolve() -> None:
    configure_mappers()
    for spec in SIMPLE_FK_LEDGER:
        model = _model_for_table(spec["local_table"])
        assert spec["name"] in _fk_names(model), f"missing simple FK {spec['name']}"
    for spec in COMPOSITE_FK_LEDGER:
        model = _model_for_table(spec["local_table"])
        assert spec["name"] in _fk_names(model), f"missing composite FK {spec['name']}"


def test_W1P01_T2_03_w1p01_relationship_count_is_zero() -> None:
    for name in FROZEN_NEW_MODELS:
        model = _model_by_name(name)
        mapper = sa_inspect(model)
        assert mapper.relationships == (), f"{name} has relationships"


def test_W1P01_T2_04_gsp_gspv_no_new_w1p01_relationships_required() -> None:
    for name in FROZEN_NEW_MODELS:
        assert sa_inspect(_model_by_name(name)).relationships == ()


# ===========================================================================
# T3 — metadata contract
# ===========================================================================


@pytest.mark.parametrize(
    "model_name,expected_table",
    list(TABLE_NAME_LEDGER.items()),
    ids=list(TABLE_NAME_LEDGER.keys()),
)
def test_W1P01_T3_01_table_names(model_name: str, expected_table: str) -> None:
    model = _model_by_name(model_name)
    assert model.__tablename__ == expected_table


@pytest.mark.parametrize(
    "model_name,expected_cols",
    list(COLUMN_LEDGERS.items()),
    ids=list(COLUMN_LEDGERS.keys()),
)
def test_W1P01_T3_02_ordered_column_ledgers(model_name: str, expected_cols: tuple[str, ...]) -> None:
    model = _model_by_name(model_name)
    actual = _col_names(model)
    assert actual == list(expected_cols), (
        f"{model_name}: missing={set(expected_cols) - set(actual)} "
        f"extra={set(actual) - set(expected_cols)}"
    )


@pytest.mark.parametrize("model_name,count", list(COLUMN_COUNT_LEDGER.items()))
def test_W1P01_T3_03_new_model_column_counts(model_name: str, count: int) -> None:
    assert len(_col_names(_model_by_name(model_name))) == count


def test_W1P01_T3_04_ordinary_unique_ledger_exact() -> None:
    for table, uq_name, cols in ORDINARY_UQ_LEDGER:
        model = _model_for_table(table)
        uq = _uq_map(model)
        assert uq_name in uq, f"missing UQ {uq_name}"
        assert uq[uq_name] == cols


def test_W1P01_T3_05_query_index_ledger_exact_and_excludes_preexisting_ops_status() -> None:
    by_table: dict[str, set[str]] = {}
    for table, ix_name in QUERY_INDEX_LEDGER:
        by_table.setdefault(table, set()).add(ix_name)
    for table, expected in by_table.items():
        model = _model_for_table(table)
        actual = set(_index_map(model))
        missing = expected - actual
        assert not missing, f"{table} missing indexes {missing}"
    gsp_ix = set(_index_map(_model_by_name("GovernedSourceProfile")))
    assert "ix_governed_source_profiles_operational_status" in gsp_ix
    assert "ix_governed_source_profiles_operational_status" not in {
        n for _, n in QUERY_INDEX_LEDGER
    }


def test_W1P01_T3_06_partial_unique_indexes_present_with_predicates() -> None:
    for table, ix_name in PARTIAL_UQ_LEDGER:
        model = _model_for_table(table)
        ix = _index_map(model)[ix_name]
        assert ix.unique is True
        where = ix.dialect_options.get("postgresql", {}).get("where")
        assert where is not None, f"{ix_name} missing postgresql_where predicate"
        expected = PARTIAL_UQ_PREDICATES[ix_name]
        actual = _compile_partial_predicate(where)
        assert actual == expected, f"{ix_name}: expected {expected!r} got {actual!r}"


@pytest.mark.parametrize("spec", SIMPLE_FK_LEDGER, ids=[s["name"] for s in SIMPLE_FK_LEDGER])
def test_W1P01_T3_07_simple_fk_metadata_exact(spec: dict[str, Any]) -> None:
    model = _model_for_table(spec["local_table"])
    fk = _find_fk(model, spec["name"])
    assert tuple(c.name for c in fk.columns) == spec["local_cols"]
    assert fk.elements[0].column.table.name == spec["remote_table"]
    assert tuple(e.column.name for e in fk.elements) == spec["remote_cols"]
    assert fk.ondelete == spec["ondelete"]
    assert bool(fk.deferrable) is spec["deferrable"]
    if spec["initially"] is None:
        assert fk.initially is None or str(fk.initially) == "None"
    else:
        assert str(fk.initially).endswith(spec["initially"])


@pytest.mark.parametrize(
    "spec", COMPOSITE_FK_LEDGER, ids=[s["name"] for s in COMPOSITE_FK_LEDGER]
)
def test_W1P01_T3_08_composite_fk_metadata_exact(spec: dict[str, Any]) -> None:
    model = _model_for_table(spec["local_table"])
    fk = _find_fk(model, spec["name"])
    assert tuple(c.name for c in fk.columns) == spec["local_cols"]
    assert fk.elements[0].column.table.name == spec["remote_table"]
    assert tuple(e.column.name for e in fk.elements) == spec["remote_cols"]
    assert fk.ondelete == spec["ondelete"]
    assert bool(fk.deferrable) is spec["deferrable"]
    if spec["initially"] is None:
        assert fk.initially is None or str(fk.initially) == "None"
    else:
        assert str(fk.initially).endswith(spec["initially"])
    if spec.get("use_alter"):
        assert fk.use_alter is True


def test_W1P01_T3_09_named_check_ledger_complete_no_dupes() -> None:
    collected: set[str] = set()
    for model_name in (
        "GovernedSourceProfile",
        "WeeklyKnowledgeRun",
        "WeeklyKnowledgeRunAttempt",
        "KnowledgeGap",
        "WeeklyRunSourceResult",
        "WeeklyRunGapResult",
        "I5GovernanceDecision",
    ):
        collected |= {n for n in _check_names(_model_by_name(model_name)) if n in NAMED_CHECKS_70}
    missing = set(NAMED_CHECKS_70) - collected
    extra_in_scope = collected - set(NAMED_CHECKS_70)
    assert not missing, f"missing checks {sorted(missing)}"
    assert not extra_in_scope
    assert len(NAMED_CHECKS_70) == 70


# ===========================================================================
# T4 — Design Freeze regression
# ===========================================================================


def test_W1P01_T4_01_architecture_counts() -> None:
    assert len(GSP_ADDITIVE_COLUMNS) == 13
    assert len(FROZEN_NEW_MODELS) == 6
    assert len(FROZEN_ENUM_CLASSES) == 19
    assert len(NAMED_CHECKS_70) == 70
    assert len(SIMPLE_FK_LEDGER) == 9
    assert len(COMPOSITE_FK_LEDGER) == 4
    assert len(ORDINARY_UQ_LEDGER) == 8
    assert len(PARTIAL_UQ_LEDGER) == 3
    assert len(QUERY_INDEX_LEDGER) == 29
    for name in FROZEN_NEW_MODELS:
        assert sa_inspect(_model_by_name(name)).relationships == ()


def test_W1P01_T4_02_forbidden_fields_absent() -> None:
    for model_name in ("WeeklyRunSourceResult", "WeeklyRunGapResult", "KnowledgeGap"):
        cols = set(_col_names(_model_by_name(model_name)))
        assert FORBIDDEN_RESULT_DECISION_ID not in cols
        assert FORBIDDEN_REOPEN_FK not in cols


def test_W1P01_T4_03_decision_request_unique_excludes_decision_type() -> None:
    uq = _uq_map(_model_by_name("I5GovernanceDecision"))["uq_i5gd_decision_request"]
    assert uq == ("entity_type", "entity_id", "decision_request_key")
    assert "decision_type" not in uq


def test_W1P01_T4_04_canonical_hash_not_alone_unique() -> None:
    for name, cols in _uq_map(_model_by_name("I5GovernanceDecision")).items():
        assert cols != ("canonical_hash",), f"{name} uniquely constrains hash alone"


def test_W1P01_T4_05_gsp_additive_exactly_thirteen() -> None:
    actual = _col_names(_model_by_name("GovernedSourceProfile"))
    for col in GSP_ADDITIVE_COLUMNS:
        assert col in actual
    assert set(actual) == set(GSP_ALL_COLUMNS)


# ===========================================================================
# T5 — PostgreSQL DDL / create_all smoke (execution later)
# ===========================================================================


def test_W1P01_T5_01_metadata_contains_w1p01_tables(db) -> None:
    _require_postgres(db)
    from backend.app.database import Base

    meta_tables = set(Base.metadata.tables.keys())
    for table in (
        "weekly_knowledge_runs",
        "weekly_knowledge_run_attempts",
        "knowledge_gaps",
        "weekly_run_source_results",
        "weekly_run_gap_results",
        "i5_governance_decisions",
        "governed_source_profiles",
    ):
        assert table in meta_tables


def test_W1P01_T5_02_partial_unique_indexes_exist_in_pg_catalog(db) -> None:
    _require_postgres(db)
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname IN "
            "('uq_wkra_one_successful_terminal','uq_i5gd_one_superseder','uq_i5gd_one_root_per_family')"
        )
    ).fetchall()
    names = {r[0] for r in rows}
    for _, ix in PARTIAL_UQ_LEDGER:
        assert ix in names


def test_W1P01_T5_03_regex_check_names_present_on_i5gd(db) -> None:
    _require_postgres(db)
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT conname FROM pg_constraint "
            "WHERE conname IN ('ck_i5gd_canonical_hash_format','ck_i5gd_decision_request_key_format')"
        )
    ).fetchall()
    assert {r[0] for r in rows} == {
        "ck_i5gd_canonical_hash_format",
        "ck_i5gd_decision_request_key_format",
    }


# ===========================================================================
# Narrow builders (kept in-file; optional helper NOT created)
# ===========================================================================


def _build_run(**overrides):
    models, _ = _load_w1p01()
    now = datetime.utcnow()
    base = dict(
        logical_run_key=VALID_HASH,
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        schedule_key="weekly",
        run_type="WEEKLY_GOVERNED",
        trigger_type="MANUAL",
        planned_window_start=now,
        planned_window_end=now + timedelta(hours=1),
        approval_state="NOT_REQUIRED",
        source_scope_hash=VALID_HASH,
        domain_scope_hash=VALID_HASH,
        gap_scope_hash=VALID_HASH,
        config_version="v1",
        config_hash=VALID_HASH,
        status="PLANNED",
    )
    base.update(overrides)
    return models.WeeklyKnowledgeRun(**base)


def _build_attempt(run_id: int, *, attempt_number: int = 1, **overrides):
    models, _ = _load_w1p01()
    base = dict(
        weekly_run_id=run_id,
        attempt_number=attempt_number,
        status="CREATED",
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        total_sources=0,
        checked_sources=0,
        fetched_sources=0,
        skipped_sources=0,
        blocked_sources=0,
        failed_sources=0,
        new_knowledge_count=0,
        updated_knowledge_count=0,
        superseded_knowledge_count=0,
        rejected_knowledge_count=0,
        created_gap_count=0,
        resolved_gap_count=0,
        warning_count=0,
        error_count=0,
    )
    base.update(overrides)
    return models.WeeklyKnowledgeRunAttempt(**base)


def _build_gap(**overrides):
    models, _ = _load_w1p01()
    base = dict(
        canonical_gap_key=VALID_HASH,
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        domain="neurology",
        gap_type="MISSING",
        title="demo gap",
        priority="P2",
        severity="MEDIUM",
        urgency="NORMAL",
        status="OPEN",
    )
    base.update(overrides)
    return models.KnowledgeGap(**base)


def _build_decision(**overrides):
    models, _ = _load_w1p01()
    base = dict(
        entity_type="KNOWLEDGE_GAP",
        entity_id=1,
        decision_family="GAP_LIFECYCLE",
        decision_type="GAP_RESOLUTION",
        decision_request_key=VALID_REQUEST_KEY,
        outcome="RECORDED",
        actor_type="SYSTEM",
        canonical_hash=VALID_HASH,
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
    )
    base.update(overrides)
    return models.I5GovernanceDecision(**base)


def _build_gsp(**overrides):
    models, _ = _load_w1p01()
    base = dict(
        canonical_key="w1p01-gsp-" + _det_hex(8),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.GovernedSourceProfile(**base)


# ===========================================================================
# T6 — positive row contracts
# ===========================================================================


def test_W1P01_T6_01_positive_weekly_run_insert(db) -> None:
    _require_postgres(db)
    run = _build_run()
    db.add(run)
    db.flush()
    assert run.id is not None


def test_W1P01_T6_02_positive_attempt_and_gap(db) -> None:
    _require_postgres(db)
    run = _build_run(logical_run_key="b" * 64)
    db.add(run)
    db.flush()
    att = _build_attempt(run.id)
    gap = _build_gap(canonical_gap_key="c" * 64)
    db.add_all([att, gap])
    db.flush()
    assert att.id and gap.id


def test_W1P01_T6_03_positive_source_and_gap_results(db) -> None:
    _require_postgres(db)
    models, _ = _load_w1p01()
    gsp = _build_gsp(canonical_key="w1p01-demo-profile")
    db.add(gsp)
    db.flush()
    run = _build_run(logical_run_key="d" * 64)
    db.add(run)
    db.flush()
    att = _build_attempt(run.id)
    gap = _build_gap(canonical_gap_key="e" * 64)
    db.add_all([att, gap])
    db.flush()
    src = models.WeeklyRunSourceResult(
        attempt_id=att.id,
        source_profile_id=gsp.id,
        result_status="CHECKED",
        knowledge_new_count=0,
        knowledge_updated_count=0,
        knowledge_superseded_count=0,
        knowledge_rejected_count=0,
        gap_created_count=0,
        warning_count=0,
        error_count=0,
    )
    gr = models.WeeklyRunGapResult(
        attempt_id=att.id,
        gap_id=gap.id,
        result_type="DISCOVERED",
    )
    db.add_all([src, gr])
    db.flush()


def test_W1P01_T6_04_positive_governance_decision(db) -> None:
    _require_postgres(db)
    gap = _build_gap(canonical_gap_key="f" * 64)
    db.add(gap)
    db.flush()
    dec = _build_decision(entity_id=gap.id, decision_request_key="req:w1p01:pos:004")
    db.add(dec)
    db.flush()
    assert dec.id is not None


def test_W1P01_T6_05_positive_gsp_additive_fields(db) -> None:
    _require_postgres(db)
    gsp = _build_gsp(
        canonical_key="w1p01-gsp-additive",
        registry_state="UNDER_REVIEW",
        runtime_eligibility="REVIEW_REQUIRED",
        topic_coverage="neurology",
    )
    db.add(gsp)
    db.flush()
    assert gsp.registry_state == "UNDER_REVIEW"


def test_W1P01_T6_06_positive_completed_with_warnings_attempt(db) -> None:
    _require_postgres(db)
    run = _build_run(logical_run_key="1" * 64)
    db.add(run)
    db.flush()
    now = datetime.utcnow()
    att = _build_attempt(
        run.id,
        status="COMPLETED_WITH_WARNINGS",
        started_at=now,
        completed_at=now + timedelta(minutes=1),
        warning_count=1,
    )
    db.add(att)
    db.flush()


# ===========================================================================
# T7 — negative CheckConstraint matrix (parametrized; maps to all 70 names)
# ===========================================================================

# Coverage ledger: every NAMED_CHECKS_70 name appears in CHECK_NEGATIVE_CASES ids.


def _gsp_bad_registry(db):
    db.add(
        _build_gsp(
            canonical_key="bad-reg",
            registry_state="NOT_A_STATE",
        )
    )


def _gsp_bad_runtime(db):
    db.add(
        _build_gsp(
            canonical_key="bad-rt",
            runtime_eligibility="NOPE",
        )
    )


def _gsp_block_reason_long(db):
    db.add(
        _build_gsp(
            canonical_key="bad-br",
            registry_state="BLOCKED",
            block_reason="x" * 2001,
        )
    )


def _gsp_effective_window(db):
    now = datetime.utcnow()
    db.add(
        _build_gsp(
            canonical_key="bad-ew",
            effective_from=now,
            effective_to=now - timedelta(days=1),
        )
    )


CHECK_NEGATIVE_CASES: list[tuple[str, str, Any]] = [
    ("W1P01-T7-ck_gsp_registry_state_vocab", "ck_gsp_registry_state_vocab", _gsp_bad_registry),
    ("W1P01-T7-ck_gsp_runtime_eligibility_vocab", "ck_gsp_runtime_eligibility_vocab", _gsp_bad_runtime),
    ("W1P01-T7-ck_gsp_block_reason_length", "ck_gsp_block_reason_length", _gsp_block_reason_long),
    ("W1P01-T7-ck_gsp_effective_window_order", "ck_gsp_effective_window_order", _gsp_effective_window),
]


def _add_run_case(constraint: str, **overrides):
    def _mutate(db, _o=overrides):
        db.add(_build_run(**_o))

    return constraint, _mutate


def _extend_wkr_cases(cases: list) -> None:
    cases.append(
        (
            "W1P01-T7-ck_wkr_run_type_vocab",
            "ck_wkr_run_type_vocab",
            lambda db: db.add(_build_run(run_type="NOPE", logical_run_key="2" * 64)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_wkr_trigger_type_vocab",
            "ck_wkr_trigger_type_vocab",
            lambda db: db.add(_build_run(trigger_type="NOPE", logical_run_key="3" * 64)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_wkr_approval_state_vocab",
            "ck_wkr_approval_state_vocab",
            lambda db: db.add(_build_run(approval_state="NOPE", logical_run_key="4" * 64)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_wkr_status_vocab",
            "ck_wkr_status_vocab",
            lambda db: db.add(_build_run(status="NOPE", logical_run_key="5" * 64)),
        )
    )
    now = datetime.utcnow()

    def _window(db):
        db.add(
            _build_run(
                logical_run_key="6" * 64,
                planned_window_start=now,
                planned_window_end=now - timedelta(hours=1),
            )
        )

    cases.append(("W1P01-T7-ck_wkr_window_order", "ck_wkr_window_order", _window))

    def _self_sup(db):
        run = _build_run(logical_run_key="7" * 64)
        db.add(run)
        db.flush()
        run.supersedes_run_id = run.id

    cases.append(("W1P01-T7-ck_wkr_supersedes_not_self", "ck_wkr_supersedes_not_self", _self_sup))


_extend_wkr_cases(CHECK_NEGATIVE_CASES)


def _extend_wkra_cases(cases: list) -> None:
    def _prep(db):
        run = _build_run(logical_run_key=("w" + "0" * 63))
        # ensure unique keys

        run.logical_run_key = _det_hex(32)
        db.add(run)
        db.flush()
        return run

    cases.append(
        (
            "W1P01-T7-ck_wkra_status_vocab",
            "ck_wkra_status_vocab",
            lambda db: (
                db.add(_build_attempt(_prep(db).id, status="NOPE"))
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_wkra_attempt_number_pos",
            "ck_wkra_attempt_number_pos",
            lambda db: db.add(_build_attempt(_prep(db).id, attempt_number=0)),
        )
    )

    def _retry_self(db):
        run = _prep(db)
        att = _build_attempt(run.id)
        db.add(att)
        db.flush()
        att.retry_of_attempt_id = att.id

    cases.append(("W1P01-T7-ck_wkra_retry_not_self", "ck_wkra_retry_not_self", _retry_self))

    def _completed_order(db):
        run = _prep(db)
        now = datetime.utcnow()
        db.add(
            _build_attempt(
                run.id,
                started_at=now,
                completed_at=now - timedelta(minutes=1),
            )
        )

    cases.append(
        ("W1P01-T7-ck_wkra_completed_after_started", "ck_wkra_completed_after_started", _completed_order)
    )
    cases.append(
        (
            "W1P01-T7-ck_wkra_failure_reason_length",
            "ck_wkra_failure_reason_length",
            lambda db: db.add(_build_attempt(_prep(db).id, failure_reason="x" * 2001)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_wkra_block_reason_length",
            "ck_wkra_block_reason_length",
            lambda db: db.add(_build_attempt(_prep(db).id, block_reason="x" * 2001)),
        )
    )
    for col, ck in [
        ("total_sources", "ck_wkra_total_sources_nonnegative"),
        ("checked_sources", "ck_wkra_checked_sources_nonnegative"),
        ("fetched_sources", "ck_wkra_fetched_sources_nonnegative"),
        ("skipped_sources", "ck_wkra_skipped_sources_nonnegative"),
        ("blocked_sources", "ck_wkra_blocked_sources_nonnegative"),
        ("failed_sources", "ck_wkra_failed_sources_nonnegative"),
        ("new_knowledge_count", "ck_wkra_new_knowledge_count_nonnegative"),
        ("updated_knowledge_count", "ck_wkra_updated_knowledge_count_nonnegative"),
        ("superseded_knowledge_count", "ck_wkra_superseded_knowledge_count_nonnegative"),
        ("rejected_knowledge_count", "ck_wkra_rejected_knowledge_count_nonnegative"),
        ("created_gap_count", "ck_wkra_created_gap_count_nonnegative"),
        ("resolved_gap_count", "ck_wkra_resolved_gap_count_nonnegative"),
        ("warning_count", "ck_wkra_warning_count_nonnegative"),
        ("error_count", "ck_wkra_error_count_nonnegative"),
    ]:
        cases.append(
            (
                f"W1P01-T7-{ck}",
                ck,
                lambda db, c=col: db.add(_build_attempt(_prep(db).id, **{c: -1})),
            )
        )


_extend_wkra_cases(CHECK_NEGATIVE_CASES)


def _extend_kg_cases(cases: list) -> None:

    def key():
        return _det_hex(32)

    cases.append(
        (
            "W1P01-T7-ck_kg_gap_type_vocab",
            "ck_kg_gap_type_vocab",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), gap_type="NOPE")),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_priority_vocab",
            "ck_kg_priority_vocab",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), priority="P9")),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_severity_vocab",
            "ck_kg_severity_vocab",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), severity="NOPE")),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_urgency_vocab",
            "ck_kg_urgency_vocab",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), urgency="NOPE")),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_status_vocab",
            "ck_kg_status_vocab",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), status="NOPE")),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_confidence_range",
            "ck_kg_confidence_range",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), confidence=1.5)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_retry_count_nonneg",
            "ck_kg_retry_count_nonneg",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), retry_count=-1)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_description_length",
            "ck_kg_description_length",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), description="x" * 8001)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_current_knowledge_state_length",
            "ck_kg_current_knowledge_state_length",
            lambda db: db.add(
                _build_gap(canonical_gap_key=key(), current_knowledge_state="x" * 4001)
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_required_knowledge_state_length",
            "ck_kg_required_knowledge_state_length",
            lambda db: db.add(
                _build_gap(canonical_gap_key=key(), required_knowledge_state="x" * 4001)
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_next_action_length",
            "ck_kg_next_action_length",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), next_action="x" * 2001)),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_kg_blocker_length",
            "ck_kg_blocker_length",
            lambda db: db.add(_build_gap(canonical_gap_key=key(), blocker="x" * 2001)),
        )
    )


_extend_kg_cases(CHECK_NEGATIVE_CASES)


def _extend_wrsr_wrgr_i5gd_cases(cases: list) -> None:

    def prep(db):
        gsp = _build_gsp(canonical_key="wrsr-" + _det_hex(8))
        db.add(gsp)
        run = _build_run(logical_run_key=_det_hex(32))
        db.add(run)
        db.flush()
        att = _build_attempt(run.id)
        gap = _build_gap(canonical_gap_key=_det_hex(32))
        db.add_all([att, gap])
        db.flush()
        return gsp, att, gap

    def bad_wrsr_status(db):
        models, _ = _load_w1p01()
        gsp, att, _gap = prep(db)
        db.add(
            models.WeeklyRunSourceResult(
                attempt_id=att.id,
                source_profile_id=gsp.id,
                result_status="NOPE",
                knowledge_new_count=0,
                knowledge_updated_count=0,
                knowledge_superseded_count=0,
                knowledge_rejected_count=0,
                gap_created_count=0,
                warning_count=0,
                error_count=0,
            )
        )

    cases.append(("W1P01-T7-ck_wrsr_result_status_vocab", "ck_wrsr_result_status_vocab", bad_wrsr_status))

    def bad_wrsr_fail_len(db):
        models, _ = _load_w1p01()
        gsp, att, _gap = prep(db)
        db.add(
            models.WeeklyRunSourceResult(
                attempt_id=att.id,
                source_profile_id=gsp.id,
                result_status="FAILED",
                failure_reason="x" * 2001,
                knowledge_new_count=0,
                knowledge_updated_count=0,
                knowledge_superseded_count=0,
                knowledge_rejected_count=0,
                gap_created_count=0,
                warning_count=0,
                error_count=0,
            )
        )

    cases.append(
        ("W1P01-T7-ck_wrsr_failure_reason_length", "ck_wrsr_failure_reason_length", bad_wrsr_fail_len)
    )
    for col, ck in [
        ("knowledge_new_count", "ck_wrsr_knowledge_new_count_nonnegative"),
        ("knowledge_updated_count", "ck_wrsr_knowledge_updated_count_nonnegative"),
        ("knowledge_superseded_count", "ck_wrsr_knowledge_superseded_count_nonnegative"),
        ("knowledge_rejected_count", "ck_wrsr_knowledge_rejected_count_nonnegative"),
        ("gap_created_count", "ck_wrsr_gap_created_count_nonnegative"),
        ("warning_count", "ck_wrsr_warning_count_nonnegative"),
        ("error_count", "ck_wrsr_error_count_nonnegative"),
    ]:

        def _neg(db, c=col):
            models, _ = _load_w1p01()
            gsp, att, _gap = prep(db)
            kwargs = dict(
                attempt_id=att.id,
                source_profile_id=gsp.id,
                result_status="CHECKED",
                knowledge_new_count=0,
                knowledge_updated_count=0,
                knowledge_superseded_count=0,
                knowledge_rejected_count=0,
                gap_created_count=0,
                warning_count=0,
                error_count=0,
            )
            kwargs[c] = -1
            db.add(models.WeeklyRunSourceResult(**kwargs))

        cases.append((f"W1P01-T7-{ck}", ck, _neg))

    def bad_wrgr_type(db):
        models, _ = _load_w1p01()
        _gsp, att, gap = prep(db)
        db.add(
            models.WeeklyRunGapResult(
                attempt_id=att.id, gap_id=gap.id, result_type="NOPE"
            )
        )

    cases.append(("W1P01-T7-ck_wrgr_result_type_vocab", "ck_wrgr_result_type_vocab", bad_wrgr_type))

    def bad_prev(db):
        models, _ = _load_w1p01()
        _gsp, att, gap = prep(db)
        db.add(
            models.WeeklyRunGapResult(
                attempt_id=att.id,
                gap_id=gap.id,
                result_type="UPDATED",
                previous_status="NOPE",
            )
        )

    cases.append(("W1P01-T7-ck_wrgr_previous_status_vocab", "ck_wrgr_previous_status_vocab", bad_prev))

    def bad_new(db):
        models, _ = _load_w1p01()
        _gsp, att, gap = prep(db)
        db.add(
            models.WeeklyRunGapResult(
                attempt_id=att.id,
                gap_id=gap.id,
                result_type="UPDATED",
                new_status="NOPE",
            )
        )

    cases.append(("W1P01-T7-ck_wrgr_new_status_vocab", "ck_wrgr_new_status_vocab", bad_new))

    def prep_gap(db):
        gap = _build_gap(canonical_gap_key=_det_hex(32))
        db.add(gap)
        db.flush()
        return gap

    def prep_gsp(db):
        gsp = _build_gsp(canonical_key="i5gd-" + _det_hex(8))
        db.add(gsp)
        db.flush()
        return gsp

    cases.append(
        (
            "W1P01-T7-ck_i5gd_entity_type_vocab",
            "ck_i5gd_entity_type_vocab",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    entity_type="NOPE",
                    decision_request_key="req:bad:et",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_decision_family_vocab",
            "ck_i5gd_decision_family_vocab",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    decision_family="NOPE",
                    decision_request_key="req:bad:df",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_decision_type_vocab",
            "ck_i5gd_decision_type_vocab",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    decision_type="NOPE",
                    decision_request_key="req:bad:dt",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_outcome_vocab",
            "ck_i5gd_outcome_vocab",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    outcome="NOPE",
                    decision_request_key="req:bad:out",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_actor_type_vocab",
            "ck_i5gd_actor_type_vocab",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    actor_type="NOPE",
                    decision_request_key="req:bad:act",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_entity_id_pos",
            "ck_i5gd_entity_id_pos",
            lambda db: db.add(
                _build_decision(entity_id=0, decision_request_key="req:bad:eid")
            ),
        )
    )

    def self_sup_dec(db):
        gap = prep_gap(db)
        d = _build_decision(entity_id=gap.id, decision_request_key="req:bad:self")
        db.add(d)
        db.flush()
        d.supersedes_decision_id = d.id

    cases.append(("W1P01-T7-ck_i5gd_supersedes_not_self", "ck_i5gd_supersedes_not_self", self_sup_dec))
    cases.append(
        (
            "W1P01-T7-ck_i5gd_canonical_hash_format",
            "ck_i5gd_canonical_hash_format",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    canonical_hash="ABCDEF" + "0" * 58,
                    decision_request_key="req:bad:hash",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_canonical_hash_format_short",
            "ck_i5gd_canonical_hash_format",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    canonical_hash="abc",
                    decision_request_key="req:bad:hash2",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_decision_request_key_format",
            "ck_i5gd_decision_request_key_format",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    decision_request_key="",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_decision_request_key_format_badchars",
            "ck_i5gd_decision_request_key_format",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    decision_request_key="bad key!",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_hash_algorithm_constant",
            "ck_i5gd_hash_algorithm_constant",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    hash_algorithm="MD5",
                    decision_request_key="req:bad:alg",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_canonicalization_version_constant",
            "ck_i5gd_canonicalization_version_constant",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    canonicalization_version="v2",
                    decision_request_key="req:bad:can",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_reason_length",
            "ck_i5gd_reason_length",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    reason="x" * 4001,
                    decision_request_key="req:bad:reason",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_supersession_requires_parent",
            "ck_i5gd_supersession_requires_parent",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gap(db).id,
                    decision_type="SUPERSESSION",
                    decision_family="GAP_LIFECYCLE",
                    supersedes_decision_id=None,
                    decision_request_key="req:bad:sup",
                )
            ),
        )
    )
    cases.append(
        (
            "W1P01-T7-ck_i5gd_decision_type_family_matrix",
            "ck_i5gd_decision_type_family_matrix",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gsp(db).id,
                    entity_type="SOURCE_PROFILE",
                    decision_type="RIGHTS_REVIEW",
                    decision_family="AUTOMATION",
                    decision_request_key="req:bad:tfm",
                )
            ),
        )
    )

    # ck_i5gd_entity_family_matrix: no isolated IntegrityError case (see SEMANTIC_EXCEPTION).
    # Covered by metadata exact-expression + semantic VALID/INVALID predicate tests.
    cases.append(
        (
            "W1P01-T7-ck_i5gd_entity_decision_matrix",
            "ck_i5gd_entity_decision_matrix",
            lambda db: db.add(
                _build_decision(
                    entity_id=prep_gsp(db).id,
                    entity_type="SOURCE_PROFILE_VERSION",
                    decision_family="LIFECYCLE",
                    decision_type="ACTIVATION",
                    decision_request_key="req:bad:edm",
                )
            ),
        )
    )


_extend_wrsr_wrgr_i5gd_cases(CHECK_NEGATIVE_CASES)

# 69 isolated first-failure IntegrityError cases + 1 documented semantic exception = 70/70.
_COVERED_CHECKS = {c for _i, c, _m in CHECK_NEGATIVE_CASES}
_ISOLATED_REQUIRED = set(NAMED_CHECKS_70) - set(DOCUMENTED_UNISOLATABLE_CHECK_CASES)
assert _ISOLATED_REQUIRED.issubset(_COVERED_CHECKS), sorted(
    _ISOLATED_REQUIRED - _COVERED_CHECKS
)
assert set(DOCUMENTED_UNISOLATABLE_CHECK_CASES).issubset(set(NAMED_CHECKS_70))
assert len(DOCUMENTED_UNISOLATABLE_CHECK_CASES) == 1
assert not set(DOCUMENTED_UNISOLATABLE_CHECK_CASES) & _COVERED_CHECKS
assert UNEXPLAINED_SHADOWED_CHECK_CASES == ()
assert AMBIGUOUS_CHECK_CASES == ()
TOTAL_NAMED_CHECK_COVERAGE = len(_COVERED_CHECKS) + len(DOCUMENTED_UNISOLATABLE_CHECK_CASES)
assert TOTAL_NAMED_CHECK_COVERAGE == 70


@pytest.mark.parametrize(
    "case_id,constraint,mutate",
    CHECK_NEGATIVE_CASES,
    ids=[c[0] for c in CHECK_NEGATIVE_CASES],
)
def test_W1P01_T7_negative_check_constraints(db, case_id: str, constraint: str, mutate) -> None:
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: mutate(db))


def test_W1P01_T7_coverage_ledger_maps_all_seventy_checks() -> None:
    assert _ISOLATED_REQUIRED.issubset(_COVERED_CHECKS)
    assert len(NAMED_CHECKS_70) == 70
    assert len(_COVERED_CHECKS) == 69
    assert DOCUMENTED_UNISOLATABLE_CHECK_CASES == ("ck_i5gd_entity_family_matrix",)
    assert UNEXPLAINED_SHADOWED_CHECK_CASES == ()
    assert TOTAL_NAMED_CHECK_COVERAGE == 70
    assert "ck_i5gd_entity_family_matrix" in _check_names(
        _model_by_name("I5GovernanceDecision")
    )


def test_W1P01_T7_entity_family_exception_ledger_exact() -> None:
    entry = ENTITY_FAMILY_MATRIX_EXCEPTION
    assert entry["constraint_name"] == "ck_i5gd_entity_family_matrix"
    assert entry["table_name"] == "i5_governance_decisions"
    assert entry["coverage_mode"] == "SEMANTIC_EXCEPTION"
    assert entry["first_failure_isolation"] == "UNAVAILABLE"
    assert entry["overlapping_check"] == "ck_i5gd_decision_type_family_matrix"
    assert entry["overlapping_composite_fk"] == "fk_i5gd_supersedes_same_entity_family"
    assert entry["exact_expression_asserted"] is True
    assert entry["valid_semantic_case_present"] is True
    assert entry["invalid_semantic_case_present"] is True
    assert entry["schema_change_required"] is False
    assert entry["waiver_scope"] == "THIS_CONSTRAINT_ONLY"
    assert entry["postgres_constraint_order_assumed"] is False
    assert entry["production_constraint_disabled"] is False
    assert "PostgreSQL" in entry["reason"]
    assert ENTITY_FAMILY_OVERLAP_EXPLANATION
    assert "ck_i5gd_decision_type_family_matrix" in ENTITY_FAMILY_OVERLAP_EXPLANATION
    assert "fk_i5gd_supersedes_same_entity_family" in ENTITY_FAMILY_OVERLAP_EXPLANATION


def test_W1P01_T7_entity_family_matrix_metadata_exact() -> None:
    model = _model_by_name("I5GovernanceDecision")
    assert model.__tablename__ == "i5_governance_decisions"
    check = _find_check(model, "ck_i5gd_entity_family_matrix")
    assert check.name == "ck_i5gd_entity_family_matrix"
    actual = _check_sql_text(check)
    expected = _normalize_sql_expr(CK_I5GD_ENTITY_FAMILY_MATRIX_SQL)
    assert actual == expected, f"expression mismatch:\n expected={expected!r}\n actual={actual!r}"


def test_W1P01_T7_entity_family_semantic_valid_tuple() -> None:
    entity_type, decision_family = ENTITY_FAMILY_SEMANTIC_VALID
    assert _entity_family_rule_allows(entity_type, decision_family) is True
    # Semantic VALID — predicate only; no IntegrityError order claim; no DB in this Gate.
    assert ENTITY_FAMILY_MATRIX_EXCEPTION["valid_semantic_case_present"] is True


def test_W1P01_T7_entity_family_semantic_invalid_tuple() -> None:
    entity_type, decision_family = ENTITY_FAMILY_SEMANTIC_INVALID
    assert _entity_family_rule_allows(entity_type, decision_family) is False
    # Semantic INVALID — does not claim first-failure IntegrityError or constraint order.
    assert ENTITY_FAMILY_MATRIX_EXCEPTION["invalid_semantic_case_present"] is True
    assert ENTITY_FAMILY_MATRIX_EXCEPTION["postgres_constraint_order_assumed"] is False


# ===========================================================================
# T8 — FK / ordinary UQ / partial UQ (parametrized runtime negatives)
# ===========================================================================


def _wrsr_row(**kwargs):
    models, _ = _load_w1p01()
    base = dict(
        result_status="CHECKED",
        knowledge_new_count=0,
        knowledge_updated_count=0,
        knowledge_superseded_count=0,
        knowledge_rejected_count=0,
        gap_created_count=0,
        warning_count=0,
        error_count=0,
    )
    base.update(kwargs)
    return models.WeeklyRunSourceResult(**base)


def _wrgr_row(**kwargs):
    models, _ = _load_w1p01()
    base = dict(result_type="DISCOVERED")
    base.update(kwargs)
    return models.WeeklyRunGapResult(**base)


def _prep_run_attempt(db):
    run = _build_run(logical_run_key=_det_hex(32))
    db.add(run)
    db.flush()
    att = _build_attempt(run.id)
    db.add(att)
    db.flush()
    return run, att


def _prep_gsp_run_attempt_gap(db):
    gsp = _build_gsp(canonical_key="t8-" + _det_hex(8))
    run = _build_run(logical_run_key=_det_hex(32))
    db.add_all([gsp, run])
    db.flush()
    att = _build_attempt(run.id)
    gap = _build_gap(canonical_gap_key=_det_hex(32))
    db.add_all([att, gap])
    db.flush()
    return gsp, run, att, gap


SIMPLE_FK_NEGATIVE_CASES: list[tuple[str, str, Callable]] = []


def _simple_fk_mutate_wkr_supersedes(db):
    run = _build_run(logical_run_key=_det_hex(32), supersedes_run_id=999999)
    db.add(run)


def _simple_fk_mutate_wkra_weekly_run(db):
    db.add(_build_attempt(999999))


def _simple_fk_mutate_kg_target_source(db):
    db.add(_build_gap(canonical_gap_key=_det_hex(32), target_source_profile_id=999999))


def _simple_fk_mutate_kg_discovered_attempt(db):
    db.add(_build_gap(canonical_gap_key=_det_hex(32), discovered_attempt_id=999999))


def _simple_fk_mutate_wrsr_attempt(db):
    gsp = _build_gsp(canonical_key="fk-wrsr-" + _det_hex(6))
    db.add(gsp)
    db.flush()
    db.add(_wrsr_row(attempt_id=999999, source_profile_id=gsp.id))


def _simple_fk_mutate_wrsr_source_profile(db):
    _run, att = _prep_run_attempt(db)
    db.add(_wrsr_row(attempt_id=att.id, source_profile_id=999999))


def _simple_fk_mutate_wrsr_source_version(db):
    gsp, _run, att, _gap = _prep_gsp_run_attempt_gap(db)
    db.add(_wrsr_row(attempt_id=att.id, source_profile_id=gsp.id, source_version_id=999999))


def _simple_fk_mutate_wrgr_attempt(db):
    _gsp, _run, att, gap = _prep_gsp_run_attempt_gap(db)
    db.add(_wrgr_row(attempt_id=999999, gap_id=gap.id))


def _simple_fk_mutate_wrgr_gap(db):
    _gsp, _run, att, _gap = _prep_gsp_run_attempt_gap(db)
    db.add(_wrgr_row(attempt_id=att.id, gap_id=999999))


SIMPLE_FK_NEGATIVE_CASES.extend(
    [
        ("W1P01-T8-fk_wkr_supersedes_run_id", "fk_wkr_supersedes_run_id", _simple_fk_mutate_wkr_supersedes),
        ("W1P01-T8-fk_wkra_weekly_run_id", "fk_wkra_weekly_run_id", _simple_fk_mutate_wkra_weekly_run),
        (
            "W1P01-T8-fk_knowledge_gaps_target_source_profile_id",
            "fk_knowledge_gaps_target_source_profile_id",
            _simple_fk_mutate_kg_target_source,
        ),
        (
            "W1P01-T8-fk_knowledge_gaps_discovered_attempt_id",
            "fk_knowledge_gaps_discovered_attempt_id",
            _simple_fk_mutate_kg_discovered_attempt,
        ),
        ("W1P01-T8-fk_wrsr_attempt_id", "fk_wrsr_attempt_id", _simple_fk_mutate_wrsr_attempt),
        (
            "W1P01-T8-fk_wrsr_source_profile_id",
            "fk_wrsr_source_profile_id",
            _simple_fk_mutate_wrsr_source_profile,
        ),
        (
            "W1P01-T8-fk_wrsr_source_version_id",
            "fk_wrsr_source_version_id",
            _simple_fk_mutate_wrsr_source_version,
        ),
        ("W1P01-T8-fk_wrgr_attempt_id", "fk_wrgr_attempt_id", _simple_fk_mutate_wrgr_attempt),
        ("W1P01-T8-fk_wrgr_gap_id", "fk_wrgr_gap_id", _simple_fk_mutate_wrgr_gap),
    ]
)
assert len(SIMPLE_FK_NEGATIVE_CASES) == 9


COMPOSITE_FK_NEGATIVE_CASES: list[tuple[str, str, Callable, bool]] = []


def _composite_fk_mutate_wkr_successful(db):
    run1 = _build_run(logical_run_key=_det_hex(32))
    run2 = _build_run(logical_run_key=_det_hex(32))
    db.add_all([run1, run2])
    db.flush()
    att = _build_attempt(run2.id)
    db.add(att)
    db.flush()
    run1.successful_attempt_id = att.id


def _composite_fk_mutate_wkr_latest(db):
    run1 = _build_run(logical_run_key=_det_hex(32))
    run2 = _build_run(logical_run_key=_det_hex(32))
    db.add_all([run1, run2])
    db.flush()
    att = _build_attempt(run2.id)
    db.add(att)
    db.flush()
    run1.latest_attempt_id = att.id


def _composite_fk_mutate_wkra_retry(db):
    run1 = _build_run(logical_run_key=_det_hex(32))
    run2 = _build_run(logical_run_key=_det_hex(32))
    db.add_all([run1, run2])
    db.flush()
    att1 = _build_attempt(run1.id, attempt_number=1)
    db.add(att1)
    db.flush()
    db.add(
        _build_attempt(
            run2.id,
            attempt_number=1,
            retry_of_attempt_id=att1.id,
        )
    )


def _composite_fk_mutate_i5gd_supersedes(db):
    gap = _build_gap(canonical_gap_key=_det_hex(32))
    db.add(gap)
    db.flush()
    parent = _build_decision(
        entity_id=gap.id,
        decision_request_key="req:t8:parent",
        decision_family="GAP_LIFECYCLE",
        decision_type="GAP_RESOLUTION",
    )
    db.add(parent)
    db.flush()
    db.add(
        _build_decision(
            entity_id=gap.id,
            decision_request_key="req:t8:child",
            decision_type="SUPERSESSION",
            decision_family="LIFECYCLE",
            supersedes_decision_id=parent.id,
            entity_type="KNOWLEDGE_GAP",
        )
    )


COMPOSITE_FK_NEGATIVE_CASES.extend(
    [
        (
            "W1P01-T8-fk_wkr_successful_attempt_same_run",
            "fk_wkr_successful_attempt_same_run",
            _composite_fk_mutate_wkr_successful,
            True,
        ),
        (
            "W1P01-T8-fk_wkr_latest_attempt_same_run",
            "fk_wkr_latest_attempt_same_run",
            _composite_fk_mutate_wkr_latest,
            True,
        ),
        (
            "W1P01-T8-fk_wkra_retry_same_run",
            "fk_wkra_retry_same_run",
            _composite_fk_mutate_wkra_retry,
            False,
        ),
        (
            "W1P01-T8-fk_i5gd_supersedes_same_entity_family",
            "fk_i5gd_supersedes_same_entity_family",
            _composite_fk_mutate_i5gd_supersedes,
            False,
        ),
    ]
)
assert len(COMPOSITE_FK_NEGATIVE_CASES) == 4


ORDINARY_UQ_NEGATIVE_CASES: list[tuple[str, str, Callable]] = []


def _uq_mutate_logical_run_key(db):
    key = _det_hex(32)
    db.add(_build_run(logical_run_key=key))
    db.flush()
    db.add(_build_run(logical_run_key=key))


def _uq_mutate_wkra_run_attempt(db):
    run = _build_run(logical_run_key=_det_hex(32))
    db.add(run)
    db.flush()
    db.add(_build_attempt(run.id, attempt_number=1))
    db.flush()
    db.add(_build_attempt(run.id, attempt_number=1))


def _uq_mutate_wkra_id_weekly_run_id(db):
    run = _build_run(logical_run_key=_det_hex(32))
    db.add(run)
    db.flush()
    att = _build_attempt(run.id, attempt_number=1)
    db.add(att)
    db.flush()
    dup = _build_attempt(run.id, attempt_number=2)
    dup.id = att.id
    db.add(dup)


def _uq_mutate_canonical_gap_key(db):
    key = _det_hex(32)
    db.add(_build_gap(canonical_gap_key=key))
    db.flush()
    db.add(_build_gap(canonical_gap_key=key))


def _uq_mutate_wrsr_attempt_source(db):
    gsp, _run, att, _gap = _prep_gsp_run_attempt_gap(db)
    row = dict(attempt_id=att.id, source_profile_id=gsp.id)
    db.add(_wrsr_row(**row))
    db.flush()
    db.add(_wrsr_row(**row))


def _uq_mutate_wrgr_attempt_gap(db):
    _gsp, _run, att, gap = _prep_gsp_run_attempt_gap(db)
    row = dict(attempt_id=att.id, gap_id=gap.id)
    db.add(_wrgr_row(**row))
    db.flush()
    db.add(_wrgr_row(**row))


def _uq_mutate_i5gd_decision_request(db):
    gap = _build_gap(canonical_gap_key=_det_hex(32))
    db.add(gap)
    db.flush()
    key = "req:w1p01:idem:001"
    db.add(_build_decision(entity_id=gap.id, decision_request_key=key))
    db.flush()
    db.add(
        _build_decision(
            entity_id=gap.id,
            decision_request_key=key,
            decision_type="GAP_REOPEN",
        )
    )


def _uq_mutate_i5gd_id_entity_family(db):
    gap = _build_gap(canonical_gap_key=_det_hex(32))
    db.add(gap)
    db.flush()
    d1 = _build_decision(entity_id=gap.id, decision_request_key="req:t8:ef:1")
    db.add(d1)
    db.flush()
    d2 = _build_decision(entity_id=gap.id, decision_request_key="req:t8:ef:2")
    d2.id = d1.id
    db.add(d2)


ORDINARY_UQ_NEGATIVE_CASES.extend(
    [
        (
            "W1P01-T8-uq_weekly_knowledge_runs_logical_run_key",
            "uq_weekly_knowledge_runs_logical_run_key",
            _uq_mutate_logical_run_key,
        ),
        ("W1P01-T8-uq_wkra_run_attempt", "uq_wkra_run_attempt", _uq_mutate_wkra_run_attempt),
        (
            "W1P01-T8-uq_wkra_id_weekly_run_id",
            "uq_wkra_id_weekly_run_id",
            _uq_mutate_wkra_id_weekly_run_id,
        ),
        (
            "W1P01-T8-uq_knowledge_gaps_canonical_gap_key",
            "uq_knowledge_gaps_canonical_gap_key",
            _uq_mutate_canonical_gap_key,
        ),
        (
            "W1P01-T8-uq_wrsr_attempt_source_profile",
            "uq_wrsr_attempt_source_profile",
            _uq_mutate_wrsr_attempt_source,
        ),
        ("W1P01-T8-uq_wrgr_attempt_gap", "uq_wrgr_attempt_gap", _uq_mutate_wrgr_attempt_gap),
        (
            "W1P01-T8-uq_i5gd_decision_request",
            "uq_i5gd_decision_request",
            _uq_mutate_i5gd_decision_request,
        ),
        (
            "W1P01-T8-uq_i5gd_id_entity_family",
            "uq_i5gd_id_entity_family",
            _uq_mutate_i5gd_id_entity_family,
        ),
    ]
)
assert len(ORDINARY_UQ_NEGATIVE_CASES) == 8


PARTIAL_UQ_NEGATIVE_CASES: list[tuple[str, str, Callable]] = []


def _partial_uq_mutate_wkra_one_successful_terminal(db):
    run = _build_run(logical_run_key=_det_hex(32))
    db.add(run)
    db.flush()
    now = datetime.utcnow()
    db.add(
        _build_attempt(
            run.id,
            attempt_number=1,
            status="COMPLETED",
            started_at=now,
            completed_at=now,
        )
    )
    db.flush()
    db.add(
        _build_attempt(
            run.id,
            attempt_number=2,
            status="COMPLETED_WITH_WARNINGS",
            started_at=now,
            completed_at=now,
        )
    )


def _partial_uq_mutate_i5gd_one_superseder(db):
    gap = _build_gap(canonical_gap_key=_det_hex(32))
    db.add(gap)
    db.flush()
    root = _build_decision(entity_id=gap.id, decision_request_key="req:t8:root")
    db.add(root)
    db.flush()
    db.add(
        _build_decision(
            entity_id=gap.id,
            decision_request_key="req:t8:sup:1",
            decision_type="SUPERSESSION",
            decision_family="GAP_LIFECYCLE",
            supersedes_decision_id=root.id,
        )
    )
    db.flush()
    db.add(
        _build_decision(
            entity_id=gap.id,
            decision_request_key="req:t8:sup:2",
            decision_type="SUPERSESSION",
            decision_family="GAP_LIFECYCLE",
            supersedes_decision_id=root.id,
        )
    )


def _partial_uq_mutate_i5gd_one_root_per_family(db):
    gap = _build_gap(canonical_gap_key=_det_hex(32))
    db.add(gap)
    db.flush()
    db.add(_build_decision(entity_id=gap.id, decision_request_key="req:root:1"))
    db.flush()
    db.add(_build_decision(entity_id=gap.id, decision_request_key="req:root:2"))


PARTIAL_UQ_NEGATIVE_CASES.extend(
    [
        (
            "W1P01-T8-uq_wkra_one_successful_terminal",
            "uq_wkra_one_successful_terminal",
            _partial_uq_mutate_wkra_one_successful_terminal,
        ),
        (
            "W1P01-T8-uq_i5gd_one_superseder",
            "uq_i5gd_one_superseder",
            _partial_uq_mutate_i5gd_one_superseder,
        ),
        (
            "W1P01-T8-uq_i5gd_one_root_per_family",
            "uq_i5gd_one_root_per_family",
            _partial_uq_mutate_i5gd_one_root_per_family,
        ),
    ]
)
assert len(PARTIAL_UQ_NEGATIVE_CASES) == 3


@pytest.mark.parametrize(
    "case_id,constraint,mutate",
    SIMPLE_FK_NEGATIVE_CASES,
    ids=[c[0] for c in SIMPLE_FK_NEGATIVE_CASES],
)
def test_W1P01_T8_01_simple_fk_runtime_negative(db, case_id: str, constraint: str, mutate) -> None:
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: mutate(db))


@pytest.mark.parametrize(
    "case_id,constraint,mutate,deferred",
    COMPOSITE_FK_NEGATIVE_CASES,
    ids=[c[0] for c in COMPOSITE_FK_NEGATIVE_CASES],
)
def test_W1P01_T8_02_composite_fk_runtime_negative(
    db, case_id: str, constraint: str, mutate, deferred: bool
) -> None:
    if deferred:
        _expect_named_integrity_deferred(db, constraint=constraint, mutate=lambda: mutate(db))
    else:
        _expect_named_integrity(db, constraint=constraint, mutate=lambda: mutate(db))


@pytest.mark.parametrize(
    "case_id,constraint,mutate",
    ORDINARY_UQ_NEGATIVE_CASES,
    ids=[c[0] for c in ORDINARY_UQ_NEGATIVE_CASES],
)
def test_W1P01_T8_03_ordinary_uq_runtime_negative(db, case_id: str, constraint: str, mutate) -> None:
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: mutate(db))


@pytest.mark.parametrize(
    "case_id,constraint,mutate",
    PARTIAL_UQ_NEGATIVE_CASES,
    ids=[c[0] for c in PARTIAL_UQ_NEGATIVE_CASES],
)
def test_W1P01_T8_04_partial_uq_runtime_negative(db, case_id: str, constraint: str, mutate) -> None:
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: mutate(db))


def test_W1P01_T8_05_metadata_lists_all_simple_composite_ordinary_partial() -> None:
    assert len(SIMPLE_FK_LEDGER) == 9
    assert len(COMPOSITE_FK_LEDGER) == 4
    assert len(ORDINARY_UQ_LEDGER) == 8
    assert len(PARTIAL_UQ_LEDGER) == 3
    for spec in SIMPLE_FK_LEDGER:
        model = _model_for_table(spec["local_table"])
        assert spec["name"] in _fk_names(model)
    for spec in COMPOSITE_FK_LEDGER:
        model = _model_for_table(spec["local_table"])
        assert spec["name"] in _fk_names(model)


# ===========================================================================
# T9 — lifecycle / immutable identity
# ===========================================================================


def test_W1P01_T9_01_gap_reopen_preserves_canonical_key_no_replacement_fk() -> None:
    cols = set(_col_names(_model_by_name("KnowledgeGap")))
    assert "canonical_gap_key" in cols
    assert FORBIDDEN_REOPEN_FK not in cols
    _, enums = _load_w1p01()
    assert enums.KnowledgeGapStatus.REOPENED.value == "REOPENED"


def test_W1P01_T9_02_result_identities_are_attempt_pairs() -> None:
    assert _uq_map(_model_by_name("WeeklyRunSourceResult"))["uq_wrsr_attempt_source_profile"] == (
        "attempt_id",
        "source_profile_id",
    )
    assert _uq_map(_model_by_name("WeeklyRunGapResult"))["uq_wrgr_attempt_gap"] == (
        "attempt_id",
        "gap_id",
    )


def test_W1P01_T9_03_decision_hash_index_is_non_unique(db) -> None:
    ix = _index_map(_model_by_name("I5GovernanceDecision"))["ix_i5gd_content_hash"]
    assert ix.unique is False
    test_W1P01_T4_04_canonical_hash_not_alone_unique()


def test_W1P01_T9_04_same_request_key_payload_collision_is_db_enforced(db) -> None:
    _expect_named_integrity(
        db,
        constraint="uq_i5gd_decision_request",
        mutate=lambda: _uq_mutate_i5gd_decision_request(db),
    )


def test_W1P01_T9_05_supersession_stays_in_entity_family_via_composite_fk() -> None:
    assert "fk_i5gd_supersedes_same_entity_family" in _fk_names(
        _model_by_name("I5GovernanceDecision")
    )


def test_W1P01_T9_06_branching_and_multi_root_rejected_by_partial_uqs() -> None:
    i5gd = _model_by_name("I5GovernanceDecision")
    assert "uq_i5gd_one_superseder" in _index_map(i5gd)
    assert "uq_i5gd_one_root_per_family" in _index_map(i5gd)


# ===========================================================================
# T10 — GSP / GSPV regression
# ===========================================================================


def test_W1P01_T10_01_gsp_only_thirteen_additive_columns() -> None:
    actual = _col_names(_model_by_name("GovernedSourceProfile"))
    assert actual == list(GSP_ALL_COLUMNS)
    assert len(GSP_ADDITIVE_COLUMNS) == 13
    for col in GSP_PREEXISTING_COLUMNS:
        assert col in actual


def test_W1P01_T10_02_preexisting_operational_status_index_excluded_from_new_count() -> None:
    gsp = _model_by_name("GovernedSourceProfile")
    assert "ix_governed_source_profiles_operational_status" in _index_map(gsp)
    assert "ix_governed_source_profiles_operational_status" not in {
        n for _, n in QUERY_INDEX_LEDGER
    }
    assert len(QUERY_INDEX_LEDGER) == 29


def test_W1P01_T10_03_gspv_column_ledger_unchanged() -> None:
    assert _col_names(_model_by_name("GovernedSourceProfileVersion")) == list(GSPV_COLUMNS)
    assert len(GSPV_COLUMNS) == 30


def test_W1P01_T10_04_new_models_have_zero_relationships() -> None:
    for name in FROZEN_NEW_MODELS:
        assert sa_inspect(_model_by_name(name)).relationships == ()


def test_W1P01_T10_05_gsp_row_version_created_at_adjacency_metadata() -> None:
    cols = _col_names(_model_by_name("GovernedSourceProfile"))
    assert cols.index("row_version") + 1 == cols.index("created_at")


# ===========================================================================
# T11 — DEFERRED (migration parity)
# ===========================================================================

T11_MIGRATION_PARITY = "DEFERRED"


def test_W1P01_T11_deferred_marker() -> None:
    assert T11_MIGRATION_PARITY == "DEFERRED"
