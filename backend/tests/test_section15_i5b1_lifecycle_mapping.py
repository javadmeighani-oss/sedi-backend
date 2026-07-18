"""Section 15-I5-B1 — Composition mapping and lifecycle invariant tests (pure; no DB)."""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
import math
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

from backend.app.services.governance.contracts import (
    AutomationStatus,
    CredentialValidityStatus,
    DataSensitivity,
    FreshnessStatus,
    GovernanceAction,
    IngestionAttemptOutcome,
    LicenseStatus,
    ObligationKind,
    PermissionDecision,
    PermissionObligation,
    PermissionScope,
    PublicationState,
    ReviewStatus,
    ScopedPermissionGrant,
    SourceOperationalStatus,
)
from backend.app.services.governance.kb_lifecycle_mapping import (
    I5_B2_REQUIRED_PERSISTENCE_FIELDS,
    I5_B_PERSISTENCE_ARCHITECTURE_LOCK,
    LEGACY_COMPATIBILITY_STRATEGY,
    LEGACY_DOCUMENT_STATUSES,
    LEGACY_REVIEW_STATUSES,
    LEGACY_RUN_STATUSES,
    LEGACY_SOURCE_INGESTION_STATUSES,
    POLICY_CHECKPOINT_SPECS,
    POLICY_DECISION_IDEMPOTENCY_FIELDS,
    PUBLICATION_RELEASE_STRATEGY,
    SOURCE_PROFILE_VERSION_STRATEGY,
    CanonicalizationError,
    GovernedLifecycleSnapshot,
    LifecycleInvariantViolation,
    LifecycleValidationResult,
    PolicyCheckpoint,
    canonicalize_policy_request,
    canonical_policy_request_fingerprint,
    checkpoint_evidence_requirements_satisfied,
    map_legacy_automation_status,
    map_legacy_ingestion_outcome,
    map_legacy_lifecycle,
    map_legacy_publication_state,
    map_legacy_review_status,
    map_legacy_source_operational_status,
    policy_checkpoint_spec,
    source_operational_status_allows_fetch,
    validate_lifecycle_invariants,
)
from backend.app.services.governance.policy_evaluator import (
    EvaluationMode,
    PolicyEvaluationRequest,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC)
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "governance"
    / "kb_lifecycle_mapping.py"
)


def _scope(**overrides) -> PermissionScope:
    base = dict(
        source_id="src-1",
        data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL,
        field_names=("title",),
        audience="end_user",
        purpose="education",
        jurisdiction="IR",
        environment="prod",
        channel="chat",
    )
    base.update(overrides)
    return PermissionScope(**base)


def _grant(**overrides) -> ScopedPermissionGrant:
    base = dict(
        grant_id="g-1",
        policy_version_id="pol-v1",
        action=GovernanceAction.FETCH,
        decision=PermissionDecision.ALLOW_EXPLICIT,
        scope=_scope(),
        valid_from=T0 - timedelta(hours=1),
        evidence_ids=("ev-1",),
        obligations=(PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),)),),
    )
    base.update(overrides)
    return ScopedPermissionGrant(**base)


def _req(**overrides) -> PolicyEvaluationRequest:
    base = dict(
        policy_version_id="pol-v1",
        scope=_scope(),
        action=GovernanceAction.FETCH,
        evaluation_at=T0,
        license_status=LicenseStatus.EXPLICIT_GRANT,
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
        credential_status=CredentialValidityStatus.ACTIVE,
        freshness_status=FreshnessStatus.FRESH,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        automation_status=AutomationStatus.MANUAL_ONLY,
        grants=(_grant(),),
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),)),
        ),
        feature_enabled=True,
        connector_enabled=True,
        automated=False,
        mode=EvaluationMode.STANDARD,
    )
    base.update(overrides)
    return PolicyEvaluationRequest(**base)


def _valid_snapshot(**overrides) -> GovernedLifecycleSnapshot:
    base = dict(
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
        ingestion_outcome=IngestionAttemptOutcome.SUCCESS_NEW_CONTENT,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.PUBLISHED,
        automation_status=AutomationStatus.MANUAL_ONLY,
        has_successful_fresh_publish_decision=True,
        scheduled_acquisition_requested=False,
        new_raw_version_created=True,
        new_document_version_created=True,
        rollback_requested=False,
        has_valid_immutable_rollback_target=False,
        referenced_raw_object_delete_requested=False,
        source_revocation_active=False,
        auto_retry_requested=False,
        global_scheduler_enabled=True,
        i5_schedule_flag_enabled=True,
        legacy_kb_schedule_flag_enabled=True,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=True,
        mapping_fail_closed=False,
        raw_object_referenced_by_published_or_evidence=False,
    )
    base.update(overrides)
    return GovernedLifecycleSnapshot(**base)


# ---------------------------------------------------------------------------
# Architecture lock
# ---------------------------------------------------------------------------


def test_architecture_lock_source_profile_strategy() -> None:
    assert (
        I5_B_PERSISTENCE_ARCHITECTURE_LOCK.source_profile_version_strategy
        == SOURCE_PROFILE_VERSION_STRATEGY
        == "CURRENT_PROFILE_PLUS_IMMUTABLE_PROFILE_VERSION"
    )


def test_architecture_lock_publication_release_strategy() -> None:
    assert (
        I5_B_PERSISTENCE_ARCHITECTURE_LOCK.publication_release_strategy
        == PUBLICATION_RELEASE_STRATEGY
        == "DEDICATED_GOVERNED_PUBLICATION_RELEASE"
    )


def test_architecture_lock_legacy_compatibility_strategy() -> None:
    assert (
        I5_B_PERSISTENCE_ARCHITECTURE_LOCK.legacy_compatibility_strategy
        == LEGACY_COMPATIBILITY_STRATEGY
        == "CONTROLLED_SEED_WITH_FAIL_CLOSED_LEGACY_READ_MAPPING"
    )


def test_architecture_lock_ingestion_run_required() -> None:
    assert I5_B_PERSISTENCE_ARCHITECTURE_LOCK.policy_ingestion_run_required is True


def test_architecture_lock_idempotency_fields_exact_order() -> None:
    assert I5_B_PERSISTENCE_ARCHITECTURE_LOCK.policy_decision_idempotency_fields == (
        "ingestion_run_id",
        "action",
        "request_fingerprint",
        "policy_version",
    )
    assert (
        I5_B_PERSISTENCE_ARCHITECTURE_LOCK.policy_decision_idempotency_fields
        == POLICY_DECISION_IDEMPOTENCY_FIELDS
    )


def test_architecture_lock_automatic_publication_false() -> None:
    assert I5_B_PERSISTENCE_ARCHITECTURE_LOCK.automatic_publication_allowed is False


# ---------------------------------------------------------------------------
# Legacy mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(LEGACY_SOURCE_INGESTION_STATUSES))
def test_legacy_source_statuses_recognized(status: str) -> None:
    mapped, reasons, manual, fail_closed = map_legacy_source_operational_status(
        legacy_ingestion_status=status,
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    assert isinstance(mapped, SourceOperationalStatus)
    if status == "active":
        assert mapped == SourceOperationalStatus.ENABLED_IDLE
        assert fail_closed is False
    elif status == "deprecated":
        assert mapped == SourceOperationalStatus.SUSPENDED
        assert fail_closed is True
    else:
        assert mapped == SourceOperationalStatus.DISABLED
        assert fail_closed is True


def test_legacy_source_missing_profile_fail_closed() -> None:
    mapped, reasons, manual, fail_closed = map_legacy_source_operational_status(
        legacy_ingestion_status="active",
        source_fetch_enabled=True,
        governed_profile_present=False,
        governed_profile_verified=False,
    )
    assert mapped == SourceOperationalStatus.DISABLED
    assert fail_closed is True
    assert "GOVERNED_PROFILE_VERSION_REQUIRED" in reasons
    assert manual is True


def test_legacy_source_fetch_disabled() -> None:
    mapped, reasons, manual, fail_closed = map_legacy_source_operational_status(
        legacy_ingestion_status="active",
        source_fetch_enabled=False,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    assert mapped == SourceOperationalStatus.ENABLED_IDLE
    assert "SOURCE_FETCH_DISABLED" in reasons
    assert fail_closed is True


def test_legacy_source_unknown_requires_manual_review() -> None:
    mapped, reasons, manual, fail_closed = map_legacy_source_operational_status(
        legacy_ingestion_status="weird",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    assert mapped == SourceOperationalStatus.DISABLED
    assert fail_closed is True
    assert manual is True
    assert "LEGACY_SOURCE_STATUS_UNKNOWN" in reasons


@pytest.mark.parametrize("status", sorted(LEGACY_RUN_STATUSES))
def test_legacy_run_statuses_mapped(status: str) -> None:
    outcome, reasons, manual, fail_closed = map_legacy_ingestion_outcome(
        run_status=status,
        review_status="pending_review",
        content_changed=True,
        error_present=False,
    )
    assert isinstance(outcome, IngestionAttemptOutcome)
    if status == "failed":
        assert outcome == IngestionAttemptOutcome.FETCH_FAILED
        assert fail_closed is True
    elif status == "running":
        assert outcome == IngestionAttemptOutcome.BLOCKED_POLICY
        assert fail_closed is True
    else:
        assert outcome == IngestionAttemptOutcome.SUCCESS_NEW_CONTENT


def test_no_change_maps_only_to_ingestion_outcome() -> None:
    outcome, reasons, _, _ = map_legacy_ingestion_outcome(
        run_status="success",
        review_status="no_change",
        content_changed=False,
        error_present=False,
    )
    assert outcome == IngestionAttemptOutcome.NO_CHANGE
    review, rev_reasons, _, _, auto = map_legacy_review_status("no_change")
    assert review == ReviewStatus.PENDING_HUMAN
    assert "NO_CHANGE_IS_INGESTION_AXIS_NOT_REVIEW" in rev_reasons
    assert auto is False


@pytest.mark.parametrize(
    "legacy,expected,auto_flag",
    [
        ("pending_review", ReviewStatus.PENDING_HUMAN, False),
        ("approved", ReviewStatus.APPROVED, False),
        ("rejected", ReviewStatus.REJECTED, False),
        ("auto_approved", ReviewStatus.APPROVED, True),
    ],
)
def test_legacy_review_status_mapping(
    legacy: str, expected: ReviewStatus, auto_flag: bool
) -> None:
    status, reasons, manual, fail_closed, auto = map_legacy_review_status(legacy)
    assert status == expected
    assert auto is auto_flag
    if auto_flag:
        assert "LEGACY_AUTO_APPROVED_OBSERVED" in reasons
        assert fail_closed is True


def test_legacy_review_unknown_and_missing() -> None:
    s1, r1, m1, f1, a1 = map_legacy_review_status(None)
    assert s1 == ReviewStatus.PENDING_HUMAN
    assert f1 is True and m1 is True and a1 is False
    s2, r2, m2, f2, a2 = map_legacy_review_status("mystery")
    assert s2 == ReviewStatus.PENDING_HUMAN
    assert "LEGACY_REVIEW_STATUS_UNKNOWN" in r2


def test_document_active_with_published_at() -> None:
    state, reasons, manual, fail_closed = map_legacy_publication_state(
        document_status="active",
        published_at_present=True,
    )
    assert state == PublicationState.PUBLISHED
    assert fail_closed is False


def test_document_active_without_published_at_fail_closed() -> None:
    state, reasons, manual, fail_closed = map_legacy_publication_state(
        document_status="active",
        published_at_present=False,
    )
    assert state == PublicationState.UNPUBLISHED
    assert fail_closed is True
    assert "ACTIVE_WITHOUT_PUBLICATION_EVIDENCE" in reasons


@pytest.mark.parametrize("status", sorted(LEGACY_DOCUMENT_STATUSES))
def test_all_legacy_document_statuses(status: str) -> None:
    state, _, _, _ = map_legacy_publication_state(
        document_status=status,
        published_at_present=(status == "active"),
    )
    assert isinstance(state, PublicationState)


def test_auto_approved_cannot_authorize_publication() -> None:
    mapping = map_legacy_lifecycle(
        legacy_ingestion_status="active",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
        run_status="success",
        review_status="auto_approved",
        content_changed=True,
        error_present=False,
        document_status="active",
        published_at_present=True,
        i5_schedule_flag_enabled=True,
        legacy_kb_schedule_flag_enabled=True,
        global_scheduler_enabled=True,
        governed_profile_automation_permitted=True,
    )
    assert mapping.legacy_auto_approved_observed is True
    assert mapping.review_status == ReviewStatus.APPROVED
    assert mapping.publication_authorized is False
    assert mapping.fail_closed is True


def test_legacy_read_mapping_does_not_authorize_automation_alone() -> None:
    status, reasons, _, fail_closed, scheduled = map_legacy_automation_status(
        i5_schedule_flag_enabled=False,
        legacy_kb_schedule_flag_enabled=True,
        global_scheduler_enabled=False,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=False,
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
    )
    assert scheduled is False
    assert status == AutomationStatus.DISABLED
    assert "LEGACY_KB_SCHEDULE_FLAG_INSUFFICIENT_ALONE" in reasons


def test_automation_and_semantics() -> None:
    status, _, _, _, scheduled = map_legacy_automation_status(
        i5_schedule_flag_enabled=True,
        legacy_kb_schedule_flag_enabled=True,
        global_scheduler_enabled=True,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=True,
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
    )
    assert status == AutomationStatus.SCHEDULED_STAGE_ONLY
    assert scheduled is True


def test_manual_acquisition_not_blocked_by_disabled_schedule() -> None:
    status, _, _, _, scheduled = map_legacy_automation_status(
        i5_schedule_flag_enabled=False,
        legacy_kb_schedule_flag_enabled=False,
        global_scheduler_enabled=False,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=True,
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
    )
    assert scheduled is False
    assert status == AutomationStatus.MANUAL_ONLY


def test_composed_lifecycle_unknown_fail_closed() -> None:
    mapping = map_legacy_lifecycle(
        legacy_ingestion_status="??? ",
        source_fetch_enabled=True,
        governed_profile_present=False,
        governed_profile_verified=False,
        run_status="completed",  # not a Gate 3 KB run status
        review_status="pending_review",
        content_changed=True,
        error_present=False,
        document_status="active",
        published_at_present=False,
        i5_schedule_flag_enabled=False,
        legacy_kb_schedule_flag_enabled=True,
        global_scheduler_enabled=False,
        governed_profile_automation_permitted=False,
    )
    assert mapping.fail_closed is True
    assert mapping.fetch_authorized is False
    assert mapping.publication_authorized is False
    assert mapping.scheduled_acquisition_authorized is False
    assert mapping.governed_source_profile_version_required is True


def test_all_observed_legacy_review_vocab_covered() -> None:
    assert LEGACY_REVIEW_STATUSES == frozenset(
        {"pending_review", "approved", "rejected", "auto_approved", "no_change"}
    )


# ---------------------------------------------------------------------------
# Lifecycle invariants
# ---------------------------------------------------------------------------


def test_valid_lifecycle_snapshot_passes() -> None:
    result = validate_lifecycle_invariants(_valid_snapshot())
    assert result.is_valid is True
    assert result.violations == ()


def test_published_without_approved_review() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(review_status=ReviewStatus.PENDING_HUMAN)
    )
    assert any(v.code == "PUBLISHED_WITHOUT_APPROVED_REVIEW" for v in result.violations)


def test_published_without_fresh_policy_decision() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(has_successful_fresh_publish_decision=False)
    )
    assert any(
        v.code == "PUBLISHED_WITHOUT_FRESH_POLICY_DECISION" for v in result.violations
    )


def test_published_with_quarantined_or_rejected_review() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(review_status=ReviewStatus.REJECTED)
    )
    assert any(
        v.code == "PUBLISHED_WITH_QUARANTINED_OR_REJECTED_REVIEW"
        for v in result.violations
    )


def test_published_while_source_revoked_or_suspended() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(source_operational_status=SourceOperationalStatus.SUSPENDED)
    )
    assert any(
        v.code == "PUBLISHED_WHILE_SOURCE_REVOKED_OR_SUSPENDED" for v in result.violations
    )
    result2 = validate_lifecycle_invariants(
        _valid_snapshot(source_revocation_active=True)
    )
    assert any(
        v.code == "PUBLISHED_WHILE_SOURCE_REVOKED_OR_SUSPENDED"
        for v in result2.violations
    )


def test_failed_terminal_auto_retryable() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            ingestion_outcome=IngestionAttemptOutcome.FETCH_FAILED,
            auto_retry_requested=True,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(v.code == "FAILED_TERMINAL_AUTO_RETRYABLE" for v in result.violations)


def test_no_change_created_raw_version() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            ingestion_outcome=IngestionAttemptOutcome.NO_CHANGE,
            new_raw_version_created=True,
            new_document_version_created=False,
        )
    )
    assert any(v.code == "NO_CHANGE_CREATED_RAW_VERSION" for v in result.violations)


def test_no_change_created_document_version() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            ingestion_outcome=IngestionAttemptOutcome.NO_CHANGE,
            new_raw_version_created=False,
            new_document_version_created=True,
        )
    )
    assert any(v.code == "NO_CHANGE_CREATED_DOCUMENT_VERSION" for v in result.violations)


def test_fetch_while_source_disabled_suspended_or_revoked() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            source_operational_status=SourceOperationalStatus.DISABLED,
            scheduled_acquisition_requested=True,
            new_raw_version_created=False,
            new_document_version_created=False,
            automation_status=AutomationStatus.SCHEDULED_STAGE_ONLY,
        )
    )
    assert any(
        v.code == "FETCH_WHILE_SOURCE_DISABLED_SUSPENDED_OR_REVOKED"
        for v in result.violations
    )


def test_scheduled_acquisition_while_disabled() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            scheduled_acquisition_requested=True,
            automation_status=AutomationStatus.DISABLED,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(
        v.code == "SCHEDULED_ACQUISITION_WHILE_DISABLED" for v in result.violations
    )


def test_scheduled_acquisition_while_global_scheduler_disabled() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            scheduled_acquisition_requested=True,
            automation_status=AutomationStatus.SCHEDULED_STAGE_ONLY,
            global_scheduler_enabled=False,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(
        v.code == "SCHEDULED_ACQUISITION_WHILE_GLOBAL_SCHEDULER_DISABLED"
        for v in result.violations
    )


def test_scheduled_acquisition_with_legacy_flag_alone() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            scheduled_acquisition_requested=True,
            automation_status=AutomationStatus.SCHEDULED_STAGE_ONLY,
            legacy_kb_schedule_flag_enabled=True,
            i5_schedule_flag_enabled=False,
            global_scheduler_enabled=True,
            source_fetch_enabled=True,
            governed_profile_automation_permitted=True,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(
        v.code == "SCHEDULED_ACQUISITION_WITH_LEGACY_FLAG_ALONE"
        for v in result.violations
    )


def test_scheduled_acquisition_while_source_fetch_disabled() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            scheduled_acquisition_requested=True,
            automation_status=AutomationStatus.SCHEDULED_STAGE_ONLY,
            source_fetch_enabled=False,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(
        v.code == "SCHEDULED_ACQUISITION_WHILE_SOURCE_FETCH_DISABLED"
        for v in result.violations
    )


def test_rollback_without_immutable_target() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            rollback_requested=True,
            has_valid_immutable_rollback_target=False,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(v.code == "ROLLBACK_WITHOUT_IMMUTABLE_TARGET" for v in result.violations)


def test_referenced_raw_object_delete_forbidden() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            referenced_raw_object_delete_requested=True,
            raw_object_referenced_by_published_or_evidence=True,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(
        v.code == "REFERENCED_RAW_OBJECT_DELETE_FORBIDDEN" for v in result.violations
    )


def test_quarantined_content_published() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(review_status=ReviewStatus.QUARANTINED)
    )
    assert any(v.code == "QUARANTINED_CONTENT_PUBLISHED" for v in result.violations)


def test_fail_closed_mapping_cannot_authorize_fetch_or_publication() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            mapping_fail_closed=True,
            scheduled_acquisition_requested=True,
            publication_state=PublicationState.UNPUBLISHED,
            review_status=ReviewStatus.PENDING_HUMAN,
            has_successful_fresh_publish_decision=False,
            automation_status=AutomationStatus.SCHEDULED_STAGE_ONLY,
            new_raw_version_created=False,
            new_document_version_created=False,
        )
    )
    assert any(
        v.code == "FAIL_CLOSED_MAPPING_AUTHORIZED_FETCH_OR_PUBLICATION"
        for v in result.violations
    )


def test_violation_ordering_deterministic() -> None:
    result = validate_lifecycle_invariants(
        _valid_snapshot(
            review_status=ReviewStatus.QUARANTINED,
            has_successful_fresh_publish_decision=False,
            mapping_fail_closed=True,
        )
    )
    codes = [v.code for v in result.violations]
    assert codes == sorted(codes, key=lambda c: (
        (
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
        ).index(c)
        if c
        in (
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
        else 999
    ))
    assert codes == list(dict.fromkeys(codes))


def test_malformed_snapshot_type_raises() -> None:
    with pytest.raises(TypeError):
        validate_lifecycle_invariants("not-a-snapshot")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Policy checkpoints
# ---------------------------------------------------------------------------


def test_every_checkpoint_maps_to_exact_action() -> None:
    expected = {
        PolicyCheckpoint.PRE_FETCH: GovernanceAction.FETCH,
        PolicyCheckpoint.PRE_RAW_STORE: GovernanceAction.STORE_RAW,
        PolicyCheckpoint.PRE_NORMALIZED_STORE: GovernanceAction.STORE_NORMALIZED,
        PolicyCheckpoint.PRE_TRANSFORM: GovernanceAction.TRANSFORM,
        PolicyCheckpoint.PRE_DERIVATION: GovernanceAction.DERIVE,
        PolicyCheckpoint.PRE_REVIEW_STAGE: GovernanceAction.STAGE_FOR_REVIEW,
        PolicyCheckpoint.PRE_PUBLISH: GovernanceAction.PUBLISH,
    }
    assert set(POLICY_CHECKPOINT_SPECS.keys()) == set(expected.keys())
    for checkpoint, action in expected.items():
        spec = policy_checkpoint_spec(checkpoint)
        assert spec.action is action
        assert isinstance(spec.action, GovernanceAction)


def test_no_invented_revoke_or_rollback_actions() -> None:
    action_values = {a.value for a in GovernanceAction}
    assert "revoke" not in action_values
    assert "rollback" not in action_values
    for spec in POLICY_CHECKPOINT_SPECS.values():
        assert spec.action in GovernanceAction


def test_publish_requires_fresh_decision_and_approval() -> None:
    spec = policy_checkpoint_spec(PolicyCheckpoint.PRE_PUBLISH)
    assert spec.human_approval_required is True
    assert spec.fresh_decision_always_required is True
    assert "human_approved_review_state" in spec.required_evidence_categories
    assert "exact_immutable_version_evidence" in spec.required_evidence_categories
    assert "fresh_policy_evaluation_at_approval" in spec.required_evidence_categories
    assert "publication_release_evidence" in spec.required_evidence_categories


def test_fetch_does_not_require_parsed_content() -> None:
    spec = policy_checkpoint_spec(PolicyCheckpoint.PRE_FETCH)
    assert spec.normalized_or_parsed_content_required is False
    assert spec.raw_content_required is False


def test_raw_store_requires_digest_evidence() -> None:
    spec = policy_checkpoint_spec(PolicyCheckpoint.PRE_RAW_STORE)
    assert spec.raw_content_required is True
    assert "raw_byte_digest" in spec.required_evidence_categories


def test_normalized_transform_derive_require_upstream_evidence() -> None:
    for cp in (
        PolicyCheckpoint.PRE_NORMALIZED_STORE,
        PolicyCheckpoint.PRE_TRANSFORM,
        PolicyCheckpoint.PRE_DERIVATION,
    ):
        spec = policy_checkpoint_spec(cp)
        assert spec.normalized_or_parsed_content_required is True
        assert len(spec.required_evidence_categories) >= 1


# ---------------------------------------------------------------------------
# Canonical fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_deterministic_mapping_order() -> None:
    r1 = _req()
    r2 = _req()
    assert canonical_policy_request_fingerprint(r1) == canonical_policy_request_fingerprint(
        r2
    )


def test_fingerprint_aware_datetime_utc_normalization() -> None:
    east = datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    utc = datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC)
    assert east.astimezone(UTC) == utc
    f1 = canonical_policy_request_fingerprint(_req(evaluation_at=east))
    f2 = canonical_policy_request_fingerprint(_req(evaluation_at=utc))
    assert f1 == f2
    canonical = canonicalize_policy_request(_req(evaluation_at=east))
    assert '"evaluation_at":"2026-07-17T12:00:00Z"' in canonical


def test_fingerprint_enum_serialization() -> None:
    canonical = json.loads(canonicalize_policy_request(_req()))
    assert canonical["action"] == "fetch"
    assert canonical["review_status"] == "approved"


def test_fingerprint_set_ordering_stability() -> None:
    # Sets appear inside nested structures via canonicalizer unit path:
    from backend.app.services.governance import kb_lifecycle_mapping as mod

    a = mod._canonicalize_value({"z", "a", "m"})
    b = mod._canonicalize_value({"m", "z", "a"})
    assert a == b == ["a", "m", "z"]


def test_fingerprint_unicode_stability() -> None:
    r = _req(scope=_scope(purpose="آموزش"))
    fp = canonical_policy_request_fingerprint(r)
    assert canonicalize_policy_request(r).encode("utf-8")
    assert fp == hashlib.sha256(
        canonicalize_policy_request(r).encode("utf-8")
    ).hexdigest()


def test_material_field_change_changes_hash() -> None:
    f1 = canonical_policy_request_fingerprint(_req(action=GovernanceAction.FETCH))
    f2 = canonical_policy_request_fingerprint(_req(action=GovernanceAction.PUBLISH))
    assert f1 != f2


def test_naive_datetime_rejected() -> None:
    # PolicyEvaluationRequest itself rejects naive evaluation_at; test canonicalizer.
    from backend.app.services.governance import kb_lifecycle_mapping as mod

    with pytest.raises(CanonicalizationError):
        mod._canonicalize_value(datetime(2026, 7, 17, 12, 0, 0))


def test_nan_infinity_rejected() -> None:
    from backend.app.services.governance import kb_lifecycle_mapping as mod

    with pytest.raises(CanonicalizationError):
        mod._canonicalize_value(float("nan"))
    with pytest.raises(CanonicalizationError):
        mod._canonicalize_value(float("inf"))
    assert math.isnan(float("nan"))


def test_unsupported_object_rejected() -> None:
    from backend.app.services.governance import kb_lifecycle_mapping as mod

    with pytest.raises(CanonicalizationError):
        mod._canonicalize_value(object())


def test_fingerprint_exactly_64_lowercase_hex() -> None:
    fp = canonical_policy_request_fingerprint(_req())
    assert len(fp) == 64
    assert fp == fp.lower()
    assert all(c in "0123456789abcdef" for c in fp)
    assert not fp.startswith("sha256:")


def test_equivalent_enum_reconstruction_stable() -> None:
    f1 = canonical_policy_request_fingerprint(
        _req(action=GovernanceAction("fetch"))
    )
    f2 = canonical_policy_request_fingerprint(
        _req(action=GovernanceAction.FETCH)
    )
    assert f1 == f2


# ---------------------------------------------------------------------------
# Field lock
# ---------------------------------------------------------------------------


def test_field_lock_required_entity_groups() -> None:
    required = {
        "governed_source_profile",
        "immutable_source_profile_version",
        "raw_acquisition_object",
        "governed_source_version",
        "governed_document_version",
        "policy_decision_record",
        "lifecycle_event",
        "publication_release",
    }
    assert set(I5_B2_REQUIRED_PERSISTENCE_FIELDS.keys()) == required
    assert isinstance(I5_B2_REQUIRED_PERSISTENCE_FIELDS, MappingProxyType)
    assert "governed_source_document_version" not in I5_B2_REQUIRED_PERSISTENCE_FIELDS


def test_field_lock_profile_version_distinct_from_current() -> None:
    assert "current_immutable_profile_version_reference" in I5_B2_REQUIRED_PERSISTENCE_FIELDS[
        "governed_source_profile"
    ]
    assert "immutable_snapshot" in I5_B2_REQUIRED_PERSISTENCE_FIELDS[
        "immutable_source_profile_version"
    ]


def test_field_lock_publication_release_explicit() -> None:
    fields = I5_B2_REQUIRED_PERSISTENCE_FIELDS["publication_release"]
    assert "exact_document_version_reference" in fields
    assert "fresh_publish_decision_reference" in fields


def test_field_lock_raw_byte_digest_distinct_from_parsed_hash() -> None:
    raw_fields = I5_B2_REQUIRED_PERSISTENCE_FIELDS["raw_acquisition_object"]
    assert "raw_byte_digest" in raw_fields
    assert "parsed_text_hash" not in raw_fields
    assert "content_hash" not in raw_fields


def test_field_lock_policy_includes_action_and_ingestion_run() -> None:
    fields = I5_B2_REQUIRED_PERSISTENCE_FIELDS["policy_decision_record"]
    assert "ingestion_run_id" in fields
    assert "action" in fields
    assert "request_fingerprint" in fields


def test_field_lock_provenance_and_version_refs() -> None:
    source = I5_B2_REQUIRED_PERSISTENCE_FIELDS["governed_source_version"]
    document = I5_B2_REQUIRED_PERSISTENCE_FIELDS["governed_document_version"]
    assert "source_profile_version_reference" in source
    assert "raw_object_reference" in source
    assert "immutable_provenance_reference" in document
    assert "document_reference" in document
    assert "parser_version" in document


def test_field_lock_no_orm_or_mutable_leak() -> None:
    for group, fields in I5_B2_REQUIRED_PERSISTENCE_FIELDS.items():
        assert isinstance(fields, tuple)
        with pytest.raises(TypeError):
            fields_list = list(fields)  # noqa: F841 — copy is fine
            I5_B2_REQUIRED_PERSISTENCE_FIELDS[group] = ("x",)  # type: ignore[index]
        for name in fields:
            assert isinstance(name, str)
            assert "Column" not in name
            assert "relationship" not in name.lower()


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------


def test_module_import_no_environment_lookup() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os" and node.attr in ("getenv", "environ", "getenvb"):
                raise AssertionError("os environment lookup forbidden in module")
        if isinstance(node, ast.Name) and node.id in ("getenv", "environ"):
            # bare names unlikely; still guard
            pass
    assert "os.getenv" not in source
    assert "os.environ" not in source
    assert "environ[" not in source


def test_no_forbidden_imports() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_substrings = (
        "sqlalchemy",
        "backend.app.models",
        "gate3",
        "kb_scheduler",
        "routers",
        "knowledge_source_fetcher",
        "requests",
        "urllib",
        "httpx",
        "psycopg",
        "alembic",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                lowered = alias.name.lower()
                assert not any(f in lowered for f in forbidden_substrings)
        if isinstance(node, ast.ImportFrom) and node.module:
            lowered = node.module.lower()
            assert not any(f in lowered for f in forbidden_substrings)
            # May import PolicyEvaluationRequest type from policy_evaluator only.
            if "policy_evaluator" in lowered:
                assert {a.name for a in node.names} == {"PolicyEvaluationRequest"}


def test_exported_structures_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        I5_B_PERSISTENCE_ARCHITECTURE_LOCK.automatic_publication_allowed = True  # type: ignore[misc]
    with pytest.raises((TypeError, AttributeError)):
        I5_B2_REQUIRED_PERSISTENCE_FIELDS["x"] = ("y",)  # type: ignore[index]
    snap = _valid_snapshot()
    with pytest.raises(FrozenInstanceError):
        snap.review_status = ReviewStatus.REJECTED  # type: ignore[misc]
    result = validate_lifecycle_invariants(
        _valid_snapshot(review_status=ReviewStatus.PENDING_HUMAN)
    )
    assert isinstance(result, LifecycleValidationResult)
    assert isinstance(result.violations[0], LifecycleInvariantViolation)
    with pytest.raises(FrozenInstanceError):
        result.violations[0].blocking = False  # type: ignore[misc]


def test_module_source_has_no_network_or_filesystem_calls() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for banned in (
        "open(",
        "Path(",
        "socket.",
        "urlopen",
        "Session(",
        "create_engine",
        "evaluate_policy(",
    ):
        assert banned not in source


def test_public_surface_inspectable() -> None:
    mod = importlib.import_module("backend.app.services.governance.kb_lifecycle_mapping")
    assert inspect.isfunction(mod.validate_lifecycle_invariants)
    assert inspect.isfunction(mod.canonical_policy_request_fingerprint)


# ---------------------------------------------------------------------------
# F-01 / F-02 / F-03 / F-04 limited-fix regressions
# ---------------------------------------------------------------------------

_PRE_FETCH_COMPLETE_EVIDENCE = (
    "source_profile_version",
    "license_policy",
    "jurisdiction_policy",
    "fetch_policy",
)

_PRE_PUBLISH_COMPLETE_EVIDENCE = (
    "human_approved_review_state",
    "exact_immutable_version_evidence",
    "fresh_policy_evaluation_at_approval",
    "publication_release_evidence",
)


def test_pre_fetch_requires_license_and_jurisdiction_evidence() -> None:
    spec = policy_checkpoint_spec(PolicyCheckpoint.PRE_FETCH)
    assert spec.required_evidence_categories == _PRE_FETCH_COMPLETE_EVIDENCE
    assert "license_policy" in spec.required_evidence_categories
    assert "jurisdiction_policy" in spec.required_evidence_categories
    assert "license_policy" != "jurisdiction_policy"
    assert "license_policy" != "fetch_policy"
    assert "jurisdiction_policy" != "fetch_policy"
    assert checkpoint_evidence_requirements_satisfied(
        PolicyCheckpoint.PRE_FETCH, _PRE_FETCH_COMPLETE_EVIDENCE
    ) is True


def test_pre_fetch_missing_license_fails_closed() -> None:
    without_license = tuple(
        c for c in _PRE_FETCH_COMPLETE_EVIDENCE if c != "license_policy"
    )
    assert checkpoint_evidence_requirements_satisfied(
        PolicyCheckpoint.PRE_FETCH, without_license
    ) is False
    assert checkpoint_evidence_requirements_satisfied(
        PolicyCheckpoint.PRE_FETCH, _PRE_FETCH_COMPLETE_EVIDENCE
    ) is True


def test_pre_fetch_missing_jurisdiction_fails_closed() -> None:
    without_jurisdiction = tuple(
        c for c in _PRE_FETCH_COMPLETE_EVIDENCE if c != "jurisdiction_policy"
    )
    assert checkpoint_evidence_requirements_satisfied(
        PolicyCheckpoint.PRE_FETCH, without_jurisdiction
    ) is False


def test_pre_fetch_source_profile_and_fetch_policy_still_required() -> None:
    for required in ("source_profile_version", "fetch_policy"):
        incomplete = tuple(c for c in _PRE_FETCH_COMPLETE_EVIDENCE if c != required)
        assert checkpoint_evidence_requirements_satisfied(
            PolicyCheckpoint.PRE_FETCH, incomplete
        ) is False


def test_pre_publish_requires_publication_release_evidence() -> None:
    spec = policy_checkpoint_spec(PolicyCheckpoint.PRE_PUBLISH)
    assert spec.required_evidence_categories == _PRE_PUBLISH_COMPLETE_EVIDENCE
    assert "publication_release_evidence" in spec.required_evidence_categories
    assert "publication_release_evidence" != "human_approved_review_state"
    assert "publication_release_evidence" != "exact_immutable_version_evidence"
    assert "publication_release_evidence" != "fresh_policy_evaluation_at_approval"
    assert checkpoint_evidence_requirements_satisfied(
        PolicyCheckpoint.PRE_PUBLISH, _PRE_PUBLISH_COMPLETE_EVIDENCE
    ) is True


def test_pre_publish_missing_publication_release_fails_closed() -> None:
    without_release = tuple(
        c for c in _PRE_PUBLISH_COMPLETE_EVIDENCE if c != "publication_release_evidence"
    )
    assert checkpoint_evidence_requirements_satisfied(
        PolicyCheckpoint.PRE_PUBLISH, without_release
    ) is False
    for required in (
        "human_approved_review_state",
        "exact_immutable_version_evidence",
        "fresh_policy_evaluation_at_approval",
    ):
        incomplete = tuple(c for c in _PRE_PUBLISH_COMPLETE_EVIDENCE if c != required)
        assert checkpoint_evidence_requirements_satisfied(
            PolicyCheckpoint.PRE_PUBLISH, incomplete
        ) is False


def test_field_lock_source_and_document_version_groups_disjoint() -> None:
    source = I5_B2_REQUIRED_PERSISTENCE_FIELDS["governed_source_version"]
    document = I5_B2_REQUIRED_PERSISTENCE_FIELDS["governed_document_version"]
    assert source == (
        "source_profile_version_reference",
        "raw_object_reference",
    )
    assert document == (
        "document_reference",
        "supersedes_reference",
        "publication_state",
        "immutable_provenance_reference",
        "parser_version",
        "normalizer_version",
        "chunker_version",
    )
    assert set(source).isdisjoint(set(document))
    former_combined = {
        "source_profile_version_reference",
        "raw_object_reference",
        "document_reference",
        "parser_version",
        "normalizer_version",
        "chunker_version",
        "supersedes_reference",
        "publication_state",
        "immutable_provenance_reference",
    }
    assert set(source) | set(document) == former_combined
    assert "governed_source_document_version" not in I5_B2_REQUIRED_PERSISTENCE_FIELDS


def test_field_lock_approved_field_authority_ownership() -> None:
    mapping = I5_B2_REQUIRED_PERSISTENCE_FIELDS
    source = mapping["governed_source_version"]
    document = mapping["governed_document_version"]
    assert mapping["governed_source_version"] == (
        "source_profile_version_reference",
        "raw_object_reference",
    )
    assert mapping["governed_document_version"] == (
        "document_reference",
        "supersedes_reference",
        "publication_state",
        "immutable_provenance_reference",
        "parser_version",
        "normalizer_version",
        "chunker_version",
    )
    assert "governed_source_document_version" not in mapping
    assert set(source).isdisjoint(set(document))
    assert set(source) | set(document) == {
        "source_profile_version_reference",
        "raw_object_reference",
        "parser_version",
        "normalizer_version",
        "chunker_version",
        "document_reference",
        "supersedes_reference",
        "publication_state",
        "immutable_provenance_reference",
    }
    for field in (
        "parser_version",
        "normalizer_version",
        "chunker_version",
        "supersedes_reference",
        "immutable_provenance_reference",
    ):
        assert field in document
        assert field not in source
    for field in (
        "source_profile_version_reference",
        "raw_object_reference",
    ):
        assert field in source
        assert field not in document
    assert isinstance(mapping, MappingProxyType)
    assert isinstance(source, tuple)
    assert isinstance(document, tuple)
    with pytest.raises(TypeError):
        mapping["governed_source_version"] = ("x",)  # type: ignore[index]


def _scheduled_kwargs(**overrides):
    base = dict(
        i5_schedule_flag_enabled=True,
        legacy_kb_schedule_flag_enabled=True,
        global_scheduler_enabled=True,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=True,
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
    )
    base.update(overrides)
    return base


def test_scheduled_and_gate_all_six_conditions_authorize() -> None:
    status, reasons, _, _, scheduled = map_legacy_automation_status(**_scheduled_kwargs())
    assert scheduled is True
    assert status == AutomationStatus.SCHEDULED_STAGE_ONLY
    assert source_operational_status_allows_fetch(
        SourceOperationalStatus.ENABLED_IDLE
    ) is True


@pytest.mark.parametrize(
    "override",
    [
        {"i5_schedule_flag_enabled": False},
        {"legacy_kb_schedule_flag_enabled": False},
        {"global_scheduler_enabled": False},
        {"source_fetch_enabled": False},
        {"governed_profile_automation_permitted": False},
        {"source_operational_status": SourceOperationalStatus.DISABLED},
    ],
)
def test_scheduled_and_gate_each_operand_independently_denies(override: dict) -> None:
    _, _, _, _, scheduled = map_legacy_automation_status(**_scheduled_kwargs(**override))
    assert scheduled is False


@pytest.mark.parametrize(
    "status",
    [
        SourceOperationalStatus.DISABLED,
        SourceOperationalStatus.SUSPENDED,
        SourceOperationalStatus.OUTAGE,
    ],
)
def test_scheduled_and_gate_non_fetchable_operational_status(
    status: SourceOperationalStatus,
) -> None:
    assert source_operational_status_allows_fetch(status) is False
    _, reasons, _, _, scheduled = map_legacy_automation_status(
        **_scheduled_kwargs(source_operational_status=status)
    )
    assert scheduled is False
    assert "SOURCE_OPERATIONAL_STATUS_BLOCKS_FETCH" in reasons


def test_scheduled_and_gate_malformed_status_fails_closed() -> None:
    with pytest.raises(TypeError):
        source_operational_status_allows_fetch("enabled_idle")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        map_legacy_automation_status(
            **_scheduled_kwargs(source_operational_status="enabled_idle")  # type: ignore[arg-type]
        )


def test_scheduled_and_gate_eligible_status_cannot_bypass_disabled_flag() -> None:
    _, _, _, _, scheduled = map_legacy_automation_status(
        **_scheduled_kwargs(
            i5_schedule_flag_enabled=False,
            source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
        )
    )
    assert scheduled is False
    _, _, _, _, scheduled2 = map_legacy_automation_status(
        **_scheduled_kwargs(
            governed_profile_automation_permitted=False,
            source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
        )
    )
    assert scheduled2 is False
