"""I5-B1 — Pure composition mapping and lifecycle invariants.

Deterministic, database-independent, side-effect-free, fail-closed.
Does not call the policy evaluator; defines composition metadata and
canonical PolicyEvaluationRequest fingerprints only.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Final, Mapping, Optional, Tuple

from backend.app.services.governance.contracts import (
    AutomationStatus,
    GovernanceAction,
    IngestionAttemptOutcome,
    PublicationState,
    ReviewStatus,
    SourceOperationalStatus,
)
from backend.app.services.governance.policy_evaluator import PolicyEvaluationRequest

# ---------------------------------------------------------------------------
# Architecture decision lock
# ---------------------------------------------------------------------------

SOURCE_PROFILE_VERSION_STRATEGY: Final[str] = (
    "CURRENT_PROFILE_PLUS_IMMUTABLE_PROFILE_VERSION"
)
PUBLICATION_RELEASE_STRATEGY: Final[str] = "DEDICATED_GOVERNED_PUBLICATION_RELEASE"
LEGACY_COMPATIBILITY_STRATEGY: Final[str] = (
    "CONTROLLED_SEED_WITH_FAIL_CLOSED_LEGACY_READ_MAPPING"
)
POLICY_DECISION_IDEMPOTENCY_FIELDS: Final[Tuple[str, ...]] = (
    "ingestion_run_id",
    "action",
    "request_fingerprint",
    "policy_version",
)


@dataclass(frozen=True)
class PersistenceArchitectureLock:
    """Immutable I5-B persistence architecture decisions for I5-B2+."""

    source_profile_version_strategy: str
    publication_release_strategy: str
    legacy_compatibility_strategy: str
    policy_decision_idempotency_fields: Tuple[str, ...]
    policy_ingestion_run_required: bool
    automatic_publication_allowed: bool


I5_B_PERSISTENCE_ARCHITECTURE_LOCK: Final[PersistenceArchitectureLock] = (
    PersistenceArchitectureLock(
        source_profile_version_strategy=SOURCE_PROFILE_VERSION_STRATEGY,
        publication_release_strategy=PUBLICATION_RELEASE_STRATEGY,
        legacy_compatibility_strategy=LEGACY_COMPATIBILITY_STRATEGY,
        policy_decision_idempotency_fields=POLICY_DECISION_IDEMPOTENCY_FIELDS,
        policy_ingestion_run_required=True,
        automatic_publication_allowed=False,
    )
)


# ---------------------------------------------------------------------------
# I5-B2 persistence field lock (planning-level; no ORM)
# ---------------------------------------------------------------------------


I5_B2_REQUIRED_PERSISTENCE_FIELDS: Final[Mapping[str, Tuple[str, ...]]] = MappingProxyType(
    {
        "governed_source_profile": (
            "current_source_id",
            "source_class",
            "source_operational_status",
            "automation_status",
            "authority_evidence_tier",
            "license_status",
            "jurisdiction",
            "language",
            "verification_method",
            "verification_evidence_reference",
            "verified_time",
            "freshness_policy",
            "policy_version",
            "current_immutable_profile_version_reference",
        ),
        "immutable_source_profile_version": (
            "source_profile_reference",
            "immutable_snapshot",
            "deterministic_snapshot_fingerprint",
            "effective_time",
            "supersedes_profile_version_reference",
            "created_time",
        ),
        "raw_acquisition_object": (
            "digest_algorithm",
            "raw_byte_digest",
            "byte_length",
            "media_type",
            "content_encoding",
            "storage_backend",
            "object_key",
            "object_version_id",
            "retention_metadata",
            "integrity_verification_time",
        ),
        # Transformation pipeline versions and generic supersession/provenance fields
        # are document-version-scoped in I5-B1.
        # Source-version equivalents require separately named fields in I5-B2.
        # Governed source version: external profile + immutable raw acquisition only.
        "governed_source_version": (
            "source_profile_version_reference",
            "raw_object_reference",
        ),
        "governed_document_version": (
            "document_reference",
            "supersedes_reference",
            "publication_state",
            "immutable_provenance_reference",
            "parser_version",
            "normalizer_version",
            "chunker_version",
        ),
        "policy_decision_record": (
            "ingestion_run_id",
            "action",
            "request_fingerprint",
            "policy_version",
            "evaluator_fingerprint",
            "request_snapshot",
            "result_snapshot",
            "decision",
            "reason_codes",
            "evaluated_time",
            "correlation_id",
            "supersedes_decision_reference",
        ),
        "lifecycle_event": (
            "event_type",
            "source_reference",
            "version_reference",
            "release_reference",
            "previous_state",
            "resulting_state",
            "decision_evidence",
            "actor_reviewer_reference",
            "reason",
            "occurred_time",
            "correlation_id",
        ),
        "publication_release": (
            "exact_document_version_reference",
            "approval_evidence",
            "fresh_publish_decision_reference",
            "published_time",
            "supersedes_release_reference",
            "revoked_or_suspended_state",
            "rollback_target_relation",
        ),
    }
)


# ---------------------------------------------------------------------------
# Lifecycle snapshot and invariant results
# ---------------------------------------------------------------------------

_TERMINAL_INGESTION_OUTCOMES: Final[frozenset[IngestionAttemptOutcome]] = frozenset(
    {
        IngestionAttemptOutcome.FETCH_FAILED,
        IngestionAttemptOutcome.PARSE_FAILED,
        IngestionAttemptOutcome.BLOCKED_POLICY,
    }
)


@dataclass(frozen=True)
class GovernedLifecycleSnapshot:
    """Independent lifecycle axes plus minimal composition evidence."""

    source_operational_status: SourceOperationalStatus
    ingestion_outcome: IngestionAttemptOutcome
    review_status: ReviewStatus
    publication_state: PublicationState
    automation_status: AutomationStatus
    has_successful_fresh_publish_decision: bool
    scheduled_acquisition_requested: bool
    new_raw_version_created: bool
    new_document_version_created: bool
    rollback_requested: bool
    has_valid_immutable_rollback_target: bool
    referenced_raw_object_delete_requested: bool
    source_revocation_active: bool = False
    auto_retry_requested: bool = False
    global_scheduler_enabled: bool = False
    i5_schedule_flag_enabled: bool = False
    legacy_kb_schedule_flag_enabled: bool = False
    source_fetch_enabled: bool = False
    governed_profile_automation_permitted: bool = False
    mapping_fail_closed: bool = False
    raw_object_referenced_by_published_or_evidence: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.source_operational_status, SourceOperationalStatus):
            raise TypeError("source_operational_status_must_be_SourceOperationalStatus")
        if not isinstance(self.ingestion_outcome, IngestionAttemptOutcome):
            raise TypeError("ingestion_outcome_must_be_IngestionAttemptOutcome")
        if not isinstance(self.review_status, ReviewStatus):
            raise TypeError("review_status_must_be_ReviewStatus")
        if not isinstance(self.publication_state, PublicationState):
            raise TypeError("publication_state_must_be_PublicationState")
        if not isinstance(self.automation_status, AutomationStatus):
            raise TypeError("automation_status_must_be_AutomationStatus")
        for name in (
            "has_successful_fresh_publish_decision",
            "scheduled_acquisition_requested",
            "new_raw_version_created",
            "new_document_version_created",
            "rollback_requested",
            "has_valid_immutable_rollback_target",
            "referenced_raw_object_delete_requested",
            "source_revocation_active",
            "auto_retry_requested",
            "global_scheduler_enabled",
            "i5_schedule_flag_enabled",
            "legacy_kb_schedule_flag_enabled",
            "source_fetch_enabled",
            "governed_profile_automation_permitted",
            "mapping_fail_closed",
            "raw_object_referenced_by_published_or_evidence",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name}_must_be_bool")


@dataclass(frozen=True)
class LifecycleInvariantViolation:
    """One deterministic cross-axis lifecycle invariant failure."""

    code: str
    message: str
    affected_axes: Tuple[str, ...]
    blocking: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("violation_code_required")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("violation_message_required")
        if not isinstance(self.affected_axes, tuple):
            raise TypeError("affected_axes_must_be_tuple")
        if not isinstance(self.blocking, bool):
            raise TypeError("blocking_must_be_bool")


@dataclass(frozen=True)
class LifecycleValidationResult:
    """Immutable ordered validation result; does not raise for invalid combos."""

    is_valid: bool
    violations: Tuple[LifecycleInvariantViolation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.violations, tuple):
            raise TypeError("violations_must_be_tuple")
        if self.is_valid and self.violations:
            raise ValueError("valid_result_cannot_have_violations")
        if (not self.is_valid) and (not self.violations):
            raise ValueError("invalid_result_requires_violations")


# ---------------------------------------------------------------------------
# Legacy mapping result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LegacyLifecycleMapping:
    """Fail-closed Gate 3 legacy → I5 contract axis mapping."""

    source_operational_status: SourceOperationalStatus
    ingestion_outcome: IngestionAttemptOutcome
    review_status: ReviewStatus
    publication_state: PublicationState
    automation_status: AutomationStatus
    all_inputs_recognized: bool
    manual_review_required: bool
    fail_closed: bool
    reason_codes: Tuple[str, ...]
    legacy_auto_approved_observed: bool
    governed_source_profile_version_required: bool
    fetch_authorized: bool
    publication_authorized: bool
    scheduled_acquisition_authorized: bool

    def __post_init__(self) -> None:
        if not isinstance(self.reason_codes, tuple):
            raise TypeError("reason_codes_must_be_tuple")
        if self.fail_closed and (self.fetch_authorized or self.publication_authorized):
            raise ValueError("fail_closed_cannot_authorize_fetch_or_publication")
        if self.legacy_auto_approved_observed and self.publication_authorized:
            raise ValueError("legacy_auto_approved_cannot_authorize_publication")


# ---------------------------------------------------------------------------
# Policy checkpoints
# ---------------------------------------------------------------------------


class PolicyCheckpoint(str, Enum):
    """Composition-layer multi-action I5-A2 policy checkpoints."""

    PRE_FETCH = "pre_fetch"
    PRE_RAW_STORE = "pre_raw_store"
    PRE_NORMALIZED_STORE = "pre_normalized_store"
    PRE_TRANSFORM = "pre_transform"
    PRE_DERIVATION = "pre_derivation"
    PRE_REVIEW_STAGE = "pre_review_stage"
    PRE_PUBLISH = "pre_publish"


@dataclass(frozen=True)
class PolicyCheckpointSpec:
    """Deterministic checkpoint requirements mapped to GovernanceAction."""

    checkpoint: PolicyCheckpoint
    action: GovernanceAction
    required_evidence_categories: Tuple[str, ...]
    raw_content_required: bool
    normalized_or_parsed_content_required: bool
    human_approval_required: bool
    fresh_decision_always_required: bool
    fail_closed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, PolicyCheckpoint):
            raise TypeError("checkpoint_must_be_PolicyCheckpoint")
        if not isinstance(self.action, GovernanceAction):
            raise TypeError("action_must_be_GovernanceAction")
        if not isinstance(self.required_evidence_categories, tuple):
            raise TypeError("required_evidence_categories_must_be_tuple")


POLICY_CHECKPOINT_SPECS: Final[Mapping[PolicyCheckpoint, PolicyCheckpointSpec]] = (
    MappingProxyType(
        {
            PolicyCheckpoint.PRE_FETCH: PolicyCheckpointSpec(
                checkpoint=PolicyCheckpoint.PRE_FETCH,
                action=GovernanceAction.FETCH,
                required_evidence_categories=(
                    "source_profile_version",
                    "license_policy",
                    "jurisdiction_policy",
                    "fetch_policy",
                ),
                raw_content_required=False,
                normalized_or_parsed_content_required=False,
                human_approval_required=False,
                fresh_decision_always_required=True,
                fail_closed=True,
            ),
            PolicyCheckpoint.PRE_RAW_STORE: PolicyCheckpointSpec(
                checkpoint=PolicyCheckpoint.PRE_RAW_STORE,
                action=GovernanceAction.STORE_RAW,
                required_evidence_categories=(
                    "raw_byte_digest",
                    "media_type",
                    "byte_length",
                ),
                raw_content_required=True,
                normalized_or_parsed_content_required=False,
                human_approval_required=False,
                fresh_decision_always_required=True,
                fail_closed=True,
            ),
            PolicyCheckpoint.PRE_NORMALIZED_STORE: PolicyCheckpointSpec(
                checkpoint=PolicyCheckpoint.PRE_NORMALIZED_STORE,
                action=GovernanceAction.STORE_NORMALIZED,
                required_evidence_categories=(
                    "raw_object_reference",
                    "normalized_content",
                    "normalizer_version",
                ),
                raw_content_required=True,
                normalized_or_parsed_content_required=True,
                human_approval_required=False,
                fresh_decision_always_required=True,
                fail_closed=True,
            ),
            PolicyCheckpoint.PRE_TRANSFORM: PolicyCheckpointSpec(
                checkpoint=PolicyCheckpoint.PRE_TRANSFORM,
                action=GovernanceAction.TRANSFORM,
                required_evidence_categories=(
                    "normalized_content",
                    "transformer_version",
                ),
                raw_content_required=False,
                normalized_or_parsed_content_required=True,
                human_approval_required=False,
                fresh_decision_always_required=True,
                fail_closed=True,
            ),
            PolicyCheckpoint.PRE_DERIVATION: PolicyCheckpointSpec(
                checkpoint=PolicyCheckpoint.PRE_DERIVATION,
                action=GovernanceAction.DERIVE,
                required_evidence_categories=(
                    "upstream_version_reference",
                    "derivation_version",
                ),
                raw_content_required=False,
                normalized_or_parsed_content_required=True,
                human_approval_required=False,
                fresh_decision_always_required=True,
                fail_closed=True,
            ),
            PolicyCheckpoint.PRE_REVIEW_STAGE: PolicyCheckpointSpec(
                checkpoint=PolicyCheckpoint.PRE_REVIEW_STAGE,
                action=GovernanceAction.STAGE_FOR_REVIEW,
                required_evidence_categories=(
                    "document_or_version_reference",
                    "staging_evidence",
                ),
                raw_content_required=False,
                normalized_or_parsed_content_required=True,
                human_approval_required=False,
                fresh_decision_always_required=True,
                fail_closed=True,
            ),
            PolicyCheckpoint.PRE_PUBLISH: PolicyCheckpointSpec(
                checkpoint=PolicyCheckpoint.PRE_PUBLISH,
                action=GovernanceAction.PUBLISH,
                required_evidence_categories=(
                    "human_approved_review_state",
                    "exact_immutable_version_evidence",
                    "fresh_policy_evaluation_at_approval",
                    "publication_release_evidence",
                ),
                raw_content_required=False,
                normalized_or_parsed_content_required=True,
                human_approval_required=True,
                fresh_decision_always_required=True,
                fail_closed=True,
            ),
        }
    )
)


def policy_checkpoint_spec(checkpoint: PolicyCheckpoint) -> PolicyCheckpointSpec:
    """Return the locked checkpoint specification; unknown checkpoints fail closed."""
    if not isinstance(checkpoint, PolicyCheckpoint):
        raise TypeError("checkpoint_must_be_PolicyCheckpoint")
    try:
        return POLICY_CHECKPOINT_SPECS[checkpoint]
    except KeyError as exc:
        raise ValueError("unsupported_policy_checkpoint") from exc


def checkpoint_evidence_requirements_satisfied(
    checkpoint: PolicyCheckpoint,
    provided_evidence_categories: Tuple[str, ...],
) -> bool:
    """Return True only when every required evidence category is provided.

    Fail-closed: missing, empty, or non-exact category identifiers do not satisfy.
    """
    spec = policy_checkpoint_spec(checkpoint)
    if not isinstance(provided_evidence_categories, tuple):
        raise TypeError("provided_evidence_categories_must_be_tuple")
    for item in provided_evidence_categories:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise ValueError("provided_evidence_category_invalid")
    provided = frozenset(provided_evidence_categories)
    if len(provided) != len(provided_evidence_categories):
        raise ValueError("provided_evidence_categories_duplicate")
    required = frozenset(spec.required_evidence_categories)
    return required.issubset(provided)


# ---------------------------------------------------------------------------
# Legacy vocabulary (Gate 3 observed stored values)
# ---------------------------------------------------------------------------

LEGACY_SOURCE_INGESTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"draft", "active", "deprecated"}
)
LEGACY_RUN_STATUSES: Final[frozenset[str]] = frozenset({"running", "success", "failed"})
LEGACY_REVIEW_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending_review", "approved", "rejected", "auto_approved", "no_change"}
)
LEGACY_DOCUMENT_STATUSES: Final[frozenset[str]] = frozenset(
    {"draft", "active", "archived"}
)
# Observed adjacent AI metadata (not primary review axis):
LEGACY_AI_REVIEW_STATUSES: Final[frozenset[str]] = frozenset(
    {"needs_review", "failed"}
)


# ---------------------------------------------------------------------------
# Legacy axis mappers
# ---------------------------------------------------------------------------


def map_legacy_source_operational_status(
    *,
    legacy_ingestion_status: Optional[str],
    source_fetch_enabled: bool,
    governed_profile_present: bool,
    governed_profile_verified: bool,
) -> Tuple[SourceOperationalStatus, Tuple[str, ...], bool, bool]:
    """Map Gate 3 source evidence to SourceOperationalStatus (fail-closed)."""
    if not isinstance(source_fetch_enabled, bool):
        raise TypeError("source_fetch_enabled_must_be_bool")
    if not isinstance(governed_profile_present, bool):
        raise TypeError("governed_profile_present_must_be_bool")
    if not isinstance(governed_profile_verified, bool):
        raise TypeError("governed_profile_verified_must_be_bool")

    reasons: list[str] = []
    fail_closed = False
    manual_review = False

    if not governed_profile_present or not governed_profile_verified:
        reasons.append("GOVERNED_PROFILE_VERSION_REQUIRED")
        fail_closed = True
        manual_review = True

    if legacy_ingestion_status is None or (
        isinstance(legacy_ingestion_status, str) and not legacy_ingestion_status.strip()
    ):
        reasons.append("LEGACY_SOURCE_STATUS_MISSING")
        return SourceOperationalStatus.DISABLED, tuple(reasons), True, True

    if not isinstance(legacy_ingestion_status, str):
        raise TypeError("legacy_ingestion_status_must_be_str_or_none")

    status = legacy_ingestion_status.strip()
    if status not in LEGACY_SOURCE_INGESTION_STATUSES:
        reasons.append("LEGACY_SOURCE_STATUS_UNKNOWN")
        return SourceOperationalStatus.DISABLED, tuple(reasons), True, True

    if status == "deprecated":
        reasons.append("LEGACY_SOURCE_DEPRECATED")
        return SourceOperationalStatus.SUSPENDED, tuple(reasons), True, True

    if status == "draft":
        reasons.append("LEGACY_SOURCE_DRAFT")
        return SourceOperationalStatus.DISABLED, tuple(reasons), fail_closed or True, True

    # status == "active"
    if not source_fetch_enabled:
        reasons.append("SOURCE_FETCH_DISABLED")
        # Active but fetch-disabled: idle/enabled without fetch permission.
        return (
            SourceOperationalStatus.ENABLED_IDLE,
            tuple(reasons),
            True,
            fail_closed or True,
        )

    if fail_closed:
        return SourceOperationalStatus.DISABLED, tuple(reasons), True, True

    return SourceOperationalStatus.ENABLED_IDLE, tuple(reasons), False, False


def map_legacy_ingestion_outcome(
    *,
    run_status: Optional[str],
    review_status: Optional[str],
    content_changed: Optional[bool],
    error_present: bool,
) -> Tuple[IngestionAttemptOutcome, Tuple[str, ...], bool, bool]:
    """Map Gate 3 run fields to IngestionAttemptOutcome; no_change stays on this axis."""
    if not isinstance(error_present, bool):
        raise TypeError("error_present_must_be_bool")
    if content_changed is not None and not isinstance(content_changed, bool):
        raise TypeError("content_changed_must_be_bool_or_none")

    reasons: list[str] = []

    if run_status is None or (isinstance(run_status, str) and not run_status.strip()):
        reasons.append("LEGACY_RUN_STATUS_MISSING")
        return IngestionAttemptOutcome.BLOCKED_POLICY, tuple(reasons), True, True

    if not isinstance(run_status, str):
        raise TypeError("run_status_must_be_str_or_none")

    status = run_status.strip()
    if status not in LEGACY_RUN_STATUSES:
        reasons.append("LEGACY_RUN_STATUS_UNKNOWN")
        return IngestionAttemptOutcome.BLOCKED_POLICY, tuple(reasons), True, True

    review = None
    if review_status is not None:
        if not isinstance(review_status, str):
            raise TypeError("review_status_must_be_str_or_none")
        review = review_status.strip()

    if status == "failed" or error_present:
        reasons.append("LEGACY_RUN_FAILED_TERMINAL")
        return IngestionAttemptOutcome.FETCH_FAILED, tuple(reasons), False, True

    if status == "running":
        reasons.append("LEGACY_RUN_IN_PROGRESS")
        return IngestionAttemptOutcome.BLOCKED_POLICY, tuple(reasons), True, True

    # status == "success"
    if review == "no_change" or content_changed is False:
        reasons.append("LEGACY_NO_CHANGE")
        return IngestionAttemptOutcome.NO_CHANGE, tuple(reasons), False, False

    if content_changed is True or review in (
        "pending_review",
        "approved",
        "rejected",
        "auto_approved",
        None,
    ):
        return IngestionAttemptOutcome.SUCCESS_NEW_CONTENT, tuple(reasons), False, False

    reasons.append("LEGACY_INGESTION_COMBINATION_UNSUPPORTED")
    return IngestionAttemptOutcome.BLOCKED_POLICY, tuple(reasons), True, True


def map_legacy_review_status(
    legacy_review_status: Optional[str],
) -> Tuple[ReviewStatus, Tuple[str, ...], bool, bool, bool]:
    """Map Gate 3 review_status; auto_approved → APPROVED with flag, not publication auth."""
    if legacy_review_status is None or (
        isinstance(legacy_review_status, str) and not legacy_review_status.strip()
    ):
        return ReviewStatus.PENDING_HUMAN, ("LEGACY_REVIEW_STATUS_MISSING",), True, True, False

    if not isinstance(legacy_review_status, str):
        raise TypeError("legacy_review_status_must_be_str_or_none")

    value = legacy_review_status.strip()
    if value == "no_change":
        # Belong to ingestion axis only; do not treat as review approval.
        return (
            ReviewStatus.PENDING_HUMAN,
            ("NO_CHANGE_IS_INGESTION_AXIS_NOT_REVIEW",),
            True,
            True,
            False,
        )
    if value == "pending_review":
        return ReviewStatus.PENDING_HUMAN, (), False, False, False
    if value == "approved":
        return ReviewStatus.APPROVED, (), False, False, False
    if value == "rejected":
        return ReviewStatus.REJECTED, (), False, False, False
    if value == "auto_approved":
        return (
            ReviewStatus.APPROVED,
            ("LEGACY_AUTO_APPROVED_OBSERVED",),
            True,
            True,
            True,
        )
    return (
        ReviewStatus.PENDING_HUMAN,
        ("LEGACY_REVIEW_STATUS_UNKNOWN",),
        True,
        True,
        False,
    )


def map_legacy_publication_state(
    *,
    document_status: Optional[str],
    published_at_present: bool,
) -> Tuple[PublicationState, Tuple[str, ...], bool, bool]:
    """Map legacy document status + published_at evidence to PublicationState."""
    if not isinstance(published_at_present, bool):
        raise TypeError("published_at_present_must_be_bool")

    if document_status is None or (
        isinstance(document_status, str) and not document_status.strip()
    ):
        return PublicationState.UNPUBLISHED, ("LEGACY_DOCUMENT_STATUS_MISSING",), True, True

    if not isinstance(document_status, str):
        raise TypeError("document_status_must_be_str_or_none")

    status = document_status.strip()
    if status not in LEGACY_DOCUMENT_STATUSES:
        return PublicationState.UNPUBLISHED, ("LEGACY_DOCUMENT_STATUS_UNKNOWN",), True, True

    if status == "draft":
        return PublicationState.UNPUBLISHED, (), False, False

    if status == "archived":
        return PublicationState.WITHDRAWN, ("LEGACY_DOCUMENT_ARCHIVED",), False, False

    # status == "active"
    if published_at_present:
        return PublicationState.PUBLISHED, (), False, False

    return (
        PublicationState.UNPUBLISHED,
        ("ACTIVE_WITHOUT_PUBLICATION_EVIDENCE",),
        True,
        True,
    )


def source_operational_status_allows_fetch(
    source_operational_status: SourceOperationalStatus,
) -> bool:
    """Return True only for fetch-eligible SourceOperationalStatus members."""
    if not isinstance(source_operational_status, SourceOperationalStatus):
        raise TypeError("source_operational_status_must_be_SourceOperationalStatus")
    return source_operational_status is SourceOperationalStatus.ENABLED_IDLE


def map_legacy_automation_status(
    *,
    i5_schedule_flag_enabled: bool,
    legacy_kb_schedule_flag_enabled: bool,
    global_scheduler_enabled: bool,
    source_fetch_enabled: bool,
    governed_profile_automation_permitted: bool,
    source_operational_status: SourceOperationalStatus,
) -> Tuple[AutomationStatus, Tuple[str, ...], bool, bool, bool]:
    """AND-gated scheduled automation; manual acquisition remains separate."""
    for name, value in (
        ("i5_schedule_flag_enabled", i5_schedule_flag_enabled),
        ("legacy_kb_schedule_flag_enabled", legacy_kb_schedule_flag_enabled),
        ("global_scheduler_enabled", global_scheduler_enabled),
        ("source_fetch_enabled", source_fetch_enabled),
        ("governed_profile_automation_permitted", governed_profile_automation_permitted),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{name}_must_be_bool")
    if not isinstance(source_operational_status, SourceOperationalStatus):
        raise TypeError("source_operational_status_must_be_SourceOperationalStatus")

    reasons: list[str] = []
    operational_allows_fetch = source_operational_status_allows_fetch(
        source_operational_status
    )
    scheduled_authorized = (
        i5_schedule_flag_enabled
        and legacy_kb_schedule_flag_enabled
        and global_scheduler_enabled
        and source_fetch_enabled
        and governed_profile_automation_permitted
        and operational_allows_fetch
    )

    if not i5_schedule_flag_enabled:
        reasons.append("I5_SCHEDULE_FLAG_DISABLED")
    if not legacy_kb_schedule_flag_enabled:
        reasons.append("LEGACY_KB_SCHEDULE_FLAG_DISABLED")
    if not global_scheduler_enabled:
        reasons.append("GLOBAL_SCHEDULER_DISABLED")
    if not source_fetch_enabled:
        reasons.append("SOURCE_FETCH_DISABLED")
    if not governed_profile_automation_permitted:
        reasons.append("GOVERNED_AUTOMATION_NOT_PERMITTED")
    if not operational_allows_fetch:
        reasons.append("SOURCE_OPERATIONAL_STATUS_BLOCKS_FETCH")
    if legacy_kb_schedule_flag_enabled and not scheduled_authorized:
        reasons.append("LEGACY_KB_SCHEDULE_FLAG_INSUFFICIENT_ALONE")

    if scheduled_authorized:
        return (
            AutomationStatus.SCHEDULED_STAGE_ONLY,
            tuple(reasons),
            False,
            False,
            True,
        )

    if source_fetch_enabled and governed_profile_automation_permitted:
        return AutomationStatus.MANUAL_ONLY, tuple(reasons), False, False, False

    return AutomationStatus.DISABLED, tuple(reasons), False, True, False


def map_legacy_lifecycle(
    *,
    legacy_ingestion_status: Optional[str],
    source_fetch_enabled: bool,
    governed_profile_present: bool,
    governed_profile_verified: bool,
    run_status: Optional[str],
    review_status: Optional[str],
    content_changed: Optional[bool],
    error_present: bool,
    document_status: Optional[str],
    published_at_present: bool,
    i5_schedule_flag_enabled: bool,
    legacy_kb_schedule_flag_enabled: bool,
    global_scheduler_enabled: bool,
    governed_profile_automation_permitted: bool,
) -> LegacyLifecycleMapping:
    """Compose all legacy axes into one fail-closed mapping result."""
    op_status, op_reasons, op_manual, op_fc = map_legacy_source_operational_status(
        legacy_ingestion_status=legacy_ingestion_status,
        source_fetch_enabled=source_fetch_enabled,
        governed_profile_present=governed_profile_present,
        governed_profile_verified=governed_profile_verified,
    )
    ing_outcome, ing_reasons, ing_manual, ing_fc = map_legacy_ingestion_outcome(
        run_status=run_status,
        review_status=review_status,
        content_changed=content_changed,
        error_present=error_present,
    )
    rev_status, rev_reasons, rev_manual, rev_fc, auto_approved = map_legacy_review_status(
        review_status
    )
    # When review_status is no_change, ingestion mapper already owns that axis;
    # keep review as PENDING_HUMAN without treating no_change as unknown review.
    pub_state, pub_reasons, pub_manual, pub_fc = map_legacy_publication_state(
        document_status=document_status,
        published_at_present=published_at_present,
    )
    auto_status, auto_reasons, auto_manual, auto_fc, sched_auth = (
        map_legacy_automation_status(
            i5_schedule_flag_enabled=i5_schedule_flag_enabled,
            legacy_kb_schedule_flag_enabled=legacy_kb_schedule_flag_enabled,
            global_scheduler_enabled=global_scheduler_enabled,
            source_fetch_enabled=source_fetch_enabled,
            governed_profile_automation_permitted=governed_profile_automation_permitted,
            source_operational_status=op_status,
        )
    )

    reasons = tuple(
        dict.fromkeys(
            (
                *op_reasons,
                *ing_reasons,
                *rev_reasons,
                *pub_reasons,
                *auto_reasons,
            )
        )
    )
    all_recognized = not any(
        code.endswith("_UNKNOWN") or code.endswith("_MISSING") for code in reasons
    )
    # no_change on review is intentional remapping, still recognized as vocabulary.
    if review_status is not None and str(review_status).strip() == "no_change":
        all_recognized = all_recognized and True

    fail_closed = bool(op_fc or ing_fc or rev_fc or pub_fc or auto_fc)
    manual_review = bool(op_manual or ing_manual or rev_manual or pub_manual or auto_manual)
    profile_required = (not governed_profile_present) or (not governed_profile_verified)

    fetch_authorized = (
        (not fail_closed)
        and source_fetch_enabled
        and governed_profile_present
        and governed_profile_verified
        and source_operational_status_allows_fetch(op_status)
    )
    # Legacy read mapping never authorizes publication.
    publication_authorized = False

    return LegacyLifecycleMapping(
        source_operational_status=op_status,
        ingestion_outcome=ing_outcome,
        review_status=rev_status,
        publication_state=pub_state,
        automation_status=auto_status,
        all_inputs_recognized=all_recognized,
        manual_review_required=manual_review or fail_closed,
        fail_closed=fail_closed,
        reason_codes=reasons,
        legacy_auto_approved_observed=auto_approved,
        governed_source_profile_version_required=profile_required or fail_closed,
        fetch_authorized=fetch_authorized,
        publication_authorized=publication_authorized,
        scheduled_acquisition_authorized=sched_auth and (not fail_closed),
    )


# ---------------------------------------------------------------------------
# Cross-axis invariants
# ---------------------------------------------------------------------------

_INVARIANT_ORDER: Final[Tuple[str, ...]] = (
    "PUBLISHED_WITHOUT_APPROVED_REVIEW",
    "PUBLISHED_WITHOUT_FRESH_POLICY_DECISION",
    "PUBLISHED_WITH_QUARANTINED_OR_REJECTED_REVIEW",
    "PUBLISHED_WHILE_SOURCE_REVOKED_OR_SUSPENDED",
    "FAILED_TERMINAL_AUTO_RETRYABLE",
    "NO_CHANGE_CREATED_RAW_VERSION",
    "NO_CHANGE_CREATED_DOCUMENT_VERSION",
    "FETCH_WHILE_SOURCE_DISABLED_SUSPENDED_OR_REVOKED",
    "SCHEDULED_ACQUISITION_WHILE_DISABLED",
    "SCHEDULED_ACQUISITION_WHILE_GLOBAL_SCHEDULER_DISABLED",
    "SCHEDULED_ACQUISITION_WITH_LEGACY_FLAG_ALONE",
    "SCHEDULED_ACQUISITION_WHILE_SOURCE_FETCH_DISABLED",
    "ROLLBACK_WITHOUT_IMMUTABLE_TARGET",
    "REFERENCED_RAW_OBJECT_DELETE_FORBIDDEN",
    "QUARANTINED_CONTENT_PUBLISHED",
    "FAIL_CLOSED_MAPPING_AUTHORIZED_FETCH_OR_PUBLICATION",
)


def validate_lifecycle_invariants(
    snapshot: GovernedLifecycleSnapshot,
) -> LifecycleValidationResult:
    """Validate cross-axis lifecycle invariants; return violations, do not raise."""
    if not isinstance(snapshot, GovernedLifecycleSnapshot):
        raise TypeError("snapshot_must_be_GovernedLifecycleSnapshot")

    found: dict[str, LifecycleInvariantViolation] = {}

    def add(
        code: str,
        message: str,
        axes: Tuple[str, ...],
        *,
        blocking: bool = True,
    ) -> None:
        if code not in found:
            found[code] = LifecycleInvariantViolation(
                code=code,
                message=message,
                affected_axes=axes,
                blocking=blocking,
            )

    published = snapshot.publication_state == PublicationState.PUBLISHED

    if published and snapshot.review_status != ReviewStatus.APPROVED:
        add(
            "PUBLISHED_WITHOUT_APPROVED_REVIEW",
            "PUBLISHED requires review APPROVED.",
            ("publication_state", "review_status"),
        )

    if published and not snapshot.has_successful_fresh_publish_decision:
        add(
            "PUBLISHED_WITHOUT_FRESH_POLICY_DECISION",
            "PUBLISHED requires a successful fresh PUBLISH policy decision.",
            ("publication_state", "policy_decision"),
        )

    if published and snapshot.review_status in (
        ReviewStatus.QUARANTINED,
        ReviewStatus.REJECTED,
    ):
        add(
            "PUBLISHED_WITH_QUARANTINED_OR_REJECTED_REVIEW",
            "PUBLISHED cannot coexist with QUARANTINED or REJECTED review state.",
            ("publication_state", "review_status"),
        )

    if published and (
        snapshot.source_revocation_active
        or snapshot.source_operational_status == SourceOperationalStatus.SUSPENDED
    ):
        add(
            "PUBLISHED_WHILE_SOURCE_REVOKED_OR_SUSPENDED",
            "PUBLISHED cannot remain active when source is revoked or suspended.",
            ("publication_state", "source_operational_status"),
        )

    if (
        snapshot.ingestion_outcome in _TERMINAL_INGESTION_OUTCOMES
        and snapshot.auto_retry_requested
    ):
        add(
            "FAILED_TERMINAL_AUTO_RETRYABLE",
            "FAILED_TERMINAL cannot be auto-retryable.",
            ("ingestion_outcome",),
        )

    if (
        snapshot.ingestion_outcome == IngestionAttemptOutcome.NO_CHANGE
        and snapshot.new_raw_version_created
    ):
        add(
            "NO_CHANGE_CREATED_RAW_VERSION",
            "NO_CHANGE cannot create a new raw version.",
            ("ingestion_outcome",),
        )

    if (
        snapshot.ingestion_outcome == IngestionAttemptOutcome.NO_CHANGE
        and snapshot.new_document_version_created
    ):
        add(
            "NO_CHANGE_CREATED_DOCUMENT_VERSION",
            "NO_CHANGE cannot create a new document version.",
            ("ingestion_outcome",),
        )

    fetch_blocked_ops = {
        SourceOperationalStatus.DISABLED,
        SourceOperationalStatus.SUSPENDED,
    }
    if snapshot.scheduled_acquisition_requested or snapshot.new_raw_version_created:
        if (
            snapshot.source_operational_status in fetch_blocked_ops
            or snapshot.source_revocation_active
        ):
            add(
                "FETCH_WHILE_SOURCE_DISABLED_SUSPENDED_OR_REVOKED",
                "Source disabled/suspended/revoked cannot perform FETCH.",
                ("source_operational_status", "ingestion_outcome"),
            )

    if snapshot.scheduled_acquisition_requested:
        if snapshot.automation_status == AutomationStatus.DISABLED:
            add(
                "SCHEDULED_ACQUISITION_WHILE_DISABLED",
                "Automation disabled prevents scheduled acquisition.",
                ("automation_status",),
            )
        if not snapshot.global_scheduler_enabled:
            add(
                "SCHEDULED_ACQUISITION_WHILE_GLOBAL_SCHEDULER_DISABLED",
                "Global scheduler disabled prevents scheduled acquisition.",
                ("automation_status",),
            )
        if (
            snapshot.legacy_kb_schedule_flag_enabled
            and not (
                snapshot.i5_schedule_flag_enabled
                and snapshot.global_scheduler_enabled
                and snapshot.source_fetch_enabled
                and snapshot.governed_profile_automation_permitted
            )
        ):
            add(
                "SCHEDULED_ACQUISITION_WITH_LEGACY_FLAG_ALONE",
                "Legacy KB schedule flag alone is insufficient.",
                ("automation_status",),
            )
        if not snapshot.source_fetch_enabled:
            add(
                "SCHEDULED_ACQUISITION_WHILE_SOURCE_FETCH_DISABLED",
                "Source-level fetch disabled prevents scheduled acquisition.",
                ("automation_status",),
            )

    if snapshot.rollback_requested and not snapshot.has_valid_immutable_rollback_target:
        add(
            "ROLLBACK_WITHOUT_IMMUTABLE_TARGET",
            "Rollback requires an existing immutable target version.",
            ("publication_state",),
        )

    if (
        snapshot.referenced_raw_object_delete_requested
        and snapshot.raw_object_referenced_by_published_or_evidence
    ):
        add(
            "REFERENCED_RAW_OBJECT_DELETE_FORBIDDEN",
            "A raw object referenced by published or evidence records cannot be deleted.",
            ("ingestion_outcome", "publication_state"),
        )

    if published and snapshot.review_status == ReviewStatus.QUARANTINED:
        add(
            "QUARANTINED_CONTENT_PUBLISHED",
            "Quarantined content cannot be published.",
            ("review_status", "publication_state"),
        )

    if snapshot.mapping_fail_closed and (
        snapshot.scheduled_acquisition_requested or published
    ):
        add(
            "FAIL_CLOSED_MAPPING_AUTHORIZED_FETCH_OR_PUBLICATION",
            "A fail-closed mapping cannot authorize fetch or publication.",
            ("source_operational_status", "publication_state"),
        )

    ordered = tuple(
        found[code] for code in _INVARIANT_ORDER if code in found
    )
    # Append any unexpected codes deterministically
    extras = tuple(
        found[code]
        for code in sorted(found.keys())
        if code not in _INVARIANT_ORDER
    )
    violations = ordered + extras
    return LifecycleValidationResult(is_valid=len(violations) == 0, violations=violations)


# ---------------------------------------------------------------------------
# Canonical policy-request serialization
# ---------------------------------------------------------------------------


class CanonicalizationError(ValueError):
    """Raised for unsupported or malformed canonicalization inputs."""


def _datetime_to_rfc3339_z(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise CanonicalizationError("naive_datetime_forbidden")
    utc = value.astimezone(timezone.utc)
    # RFC3339 with Z; preserve microseconds when present.
    text = utc.isoformat().replace("+00:00", "Z")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def _canonicalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _datetime_to_rfc3339_z(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("non_finite_float_forbidden")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        raise CanonicalizationError("bytes_unsupported")
    if is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {}
        for f in fields(value):
            out[f.name] = _canonicalize_value(getattr(value, f.name))
        return out
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _canonicalize_value(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        items = []
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalizationError("mapping_keys_must_be_str")
            items.append((k, _canonicalize_value(v)))
        items.sort(key=lambda pair: pair[0])
        return {k: v for k, v in items}
    if isinstance(value, (list, tuple)):
        return [_canonicalize_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        canonical_items = [_canonicalize_value(item) for item in value]
        return sorted(
            canonical_items,
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ),
        )
    raise CanonicalizationError(f"unsupported_type:{type(value).__name__}")


def canonicalize_policy_request(request: PolicyEvaluationRequest) -> str:
    """Return canonical JSON for an exact PolicyEvaluationRequest."""
    if not isinstance(request, PolicyEvaluationRequest):
        raise TypeError("request_must_be_PolicyEvaluationRequest")
    payload = _canonicalize_value(request)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_policy_request_fingerprint(request: PolicyEvaluationRequest) -> str:
    """SHA-256 lowercase hex fingerprint of the canonical request JSON (64 chars)."""
    canonical = canonicalize_policy_request(request)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if len(digest) != 64 or digest != digest.lower() or any(c not in "0123456789abcdef" for c in digest):
        raise RuntimeError("fingerprint_format_invariant_broken")
    return digest
