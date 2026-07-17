"""Section 15-I5-A2 — Pure policy evaluator tests (isolated; no DB)."""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.services.governance.contracts import (
    AutomationStatus,
    CredentialValidityStatus,
    DataSensitivity,
    FreshnessStatus,
    GovernanceAction,
    LicenseStatus,
    ObligationKind,
    PermissionDecision,
    PermissionObligation,
    PermissionScope,
    PolicyOutcome,
    PublicationState,
    ReviewStatus,
    ScopedPermissionGrant,
    SourceOperationalStatus,
)
from backend.app.services.governance.policy_evaluator import (
    EVALUATOR_ALGORITHM_VERSION,
    EvaluationMode,
    PolicyEvaluationRequest,
    PolicyEvaluationResult,
    PolicyReasonCode,
    _decision_fingerprint,
    evaluate_policy,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)


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
        action=GovernanceAction.CITE_LINK,
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
        action=GovernanceAction.CITE_LINK,
        evaluation_at=T0,
        license_status=LicenseStatus.EXPLICIT_GRANT,
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
        credential_status=CredentialValidityStatus.ACTIVE,
        freshness_status=FreshnessStatus.FRESH,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.PUBLISHED,
        automation_status=AutomationStatus.SCHEDULED_STAGE_ONLY,
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


# --- request/result invariants ---


def test_invalid_naive_request_denied():
    with pytest.raises(ValueError, match="timezone_aware"):
        _req(evaluation_at=datetime(2026, 7, 16, 12, 0, 0))


def test_request_result_immutable():
    r = _req()
    with pytest.raises(FrozenInstanceError):
        r.feature_enabled = False  # type: ignore[misc]
    result = evaluate_policy(r)
    with pytest.raises(FrozenInstanceError):
        result.outcome = PolicyOutcome.DENY  # type: ignore[misc]


def test_duplicate_grants_rejected():
    g = _grant()
    with pytest.raises(ValueError, match="grants_duplicate"):
        _req(grants=(g, g))


# --- credential / source / license ---


def test_revoked_overrides_allow():
    r = _req(credential_status=CredentialValidityStatus.REVOKED)
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_REVOKED


def test_suspended_credential_overrides_allow():
    r = _req(credential_status=CredentialValidityStatus.SUSPENDED)
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_SUSPENDED


def test_credential_expired_denied():
    r = _req(credential_status=CredentialValidityStatus.EXPIRED)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_EXPIRED


def test_unverified_professional_directory_point_lookup_denied():
    r = _req(
        action=GovernanceAction.POINT_LOOKUP,
        scope=_scope(data_sensitivity=DataSensitivity.PROFESSIONAL_DIRECTORY),
        credential_status=CredentialValidityStatus.UNVERIFIED,
        grants=(_grant(action=GovernanceAction.POINT_LOOKUP),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_UNVERIFIED


def test_unknown_professional_directory_point_lookup_denied():
    r = _req(
        action=GovernanceAction.POINT_LOOKUP,
        scope=_scope(data_sensitivity=DataSensitivity.PROFESSIONAL_DIRECTORY),
        credential_status=CredentialValidityStatus.UNKNOWN,
        grants=(_grant(action=GovernanceAction.POINT_LOOKUP),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_UNVERIFIED


def test_unverified_contact_pii_display_fields_denied():
    r = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(
            data_sensitivity=DataSensitivity.CONTACT_PII,
            field_names=("phone",),
        ),
        credential_status=CredentialValidityStatus.UNVERIFIED,
        grants=(
            _grant(
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(
                    data_sensitivity=DataSensitivity.CONTACT_PII,
                    field_names=("phone",),
                ),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_UNVERIFIED


def test_unknown_contact_pii_display_fields_denied():
    r = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(
            data_sensitivity=DataSensitivity.CONTACT_PII,
            field_names=("phone",),
        ),
        credential_status=CredentialValidityStatus.UNKNOWN,
        grants=(
            _grant(
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(
                    data_sensitivity=DataSensitivity.CONTACT_PII,
                    field_names=("phone",),
                ),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_UNVERIFIED


def test_unverified_public_educational_cite_not_denied_for_credential():
    r = _req(
        action=GovernanceAction.CITE_LINK,
        scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
        credential_status=CredentialValidityStatus.UNVERIFIED,
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),)),
        ),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT


def test_source_suspended():
    r = _req(source_operational_status=SourceOperationalStatus.SUSPENDED)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.SOURCE_SUSPENDED


def test_license_unknown():
    r = _req(license_status=LicenseStatus.UNKNOWN)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.LICENSE_UNKNOWN


def test_license_expired():
    r = _req(license_status=LicenseStatus.EXPIRED)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.LICENSE_EXPIRED


def test_license_conflict():
    r = _req(license_status=LicenseStatus.CONFLICT)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.LICENSE_CONFLICT


def test_restricted_without_grant_denied():
    r = _req(
        license_status=LicenseStatus.RESTRICTED,
        grants=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY


# --- grant resolution ---


def test_policy_conflict_overrides():
    r = _req(
        grants=(
            _grant(decision=PermissionDecision.POLICY_CONFLICT),
        ),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.POLICY_CONFLICT


def test_explicit_deny_overrides_allow():
    r = _req(
        grants=(
            _grant(decision=PermissionDecision.ALLOW_EXPLICIT),
            _grant(grant_id="g-deny", decision=PermissionDecision.DENY_EXPLICIT),
        ),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.EXPLICIT_DENY


def test_no_matching_grant():
    r = _req(grants=(), action=GovernanceAction.FETCH)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.NO_MATCHING_GRANT


def test_policy_version_mismatch():
    r = _req(
        grants=(_grant(policy_version_id="other-v"),),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.NO_MATCHING_GRANT


def test_expired_grant():
    r = _req(
        grants=(
            _grant(
                valid_from=T0 - timedelta(days=10),
                valid_until=T0 - timedelta(days=1),
            ),
        ),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.GRANT_EXPIRED


def test_resource_mismatch():
    r = _req(
        scope=_scope(resource_id="res-a"),
        grants=(_grant(scope=_scope(resource_id="res-b")),),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.NO_MATCHING_GRANT


def test_source_level_grant_cannot_cover_resource():
    r = _req(
        scope=_scope(resource_id="res-a"),
        grants=(_grant(scope=_scope(resource_id=None)),),
        action=GovernanceAction.FETCH,
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY


def test_grant_order_permutation_invariant():
    g_a = _grant(grant_id="g-a", obligations=())
    g_b = _grant(grant_id="g-b", obligations=())
    r1 = _req(grants=(g_a, g_b), fulfilled_obligations=())
    r2 = _req(grants=(g_b, g_a), fulfilled_obligations=())
    res1 = evaluate_policy(r1)
    res2 = evaluate_policy(r2)
    assert res1.outcome is res2.outcome
    assert res1.primary_reason is res2.primary_reason
    assert res1.reason_codes == res2.reason_codes
    assert res1.matched_grant_ids == ("g-a", "g-b")
    assert res2.matched_grant_ids == ("g-a", "g-b")
    assert res1.decision_fingerprint == res2.decision_fingerprint


# --- display fields ---


def test_display_fields_fully_covered():
    r = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(field_names=("title", "summary")),
        grants=(
            _grant(
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(field_names=("title", "summary")),
            ),
        ),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW


def test_multiple_allow_grants_union_field_coverage():
    r = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(field_names=("title", "summary")),
        grants=(
            _grant(
                grant_id="g-title",
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(field_names=("title",)),
                obligations=(),
            ),
            _grant(
                grant_id="g-summary",
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(field_names=("summary",)),
                obligations=(),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.matched_grant_ids == ("g-summary", "g-title")


def test_one_denied_field_blocks_display():
    r = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(field_names=("phone", "title")),
        grants=(
            _grant(
                grant_id="g-allow",
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(field_names=("title",)),
            ),
            _grant(
                grant_id="g-deny",
                action=GovernanceAction.DISPLAY_FIELDS,
                decision=PermissionDecision.DENY_EXPLICIT,
                scope=_scope(field_names=("phone",)),
            ),
        ),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.EXPLICIT_DENY


def test_contact_pii_requires_field_allow():
    r = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(
            data_sensitivity=DataSensitivity.CONTACT_PII,
            field_names=("phone",),
        ),
        grants=(
            _grant(
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(
                    data_sensitivity=DataSensitivity.CONTACT_PII,
                    field_names=("title",),
                ),
            ),
        ),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.FIELD_SCOPE_NOT_COVERED


def test_field_names_order_permutation_fingerprint_invariant():
    r1 = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(field_names=("title", "summary")),
        grants=(
            _grant(
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(field_names=("title", "summary")),
            ),
        ),
    )
    r2 = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(field_names=("summary", "title")),
        grants=(
            _grant(
                action=GovernanceAction.DISPLAY_FIELDS,
                scope=_scope(field_names=("summary", "title")),
            ),
        ),
    )
    fp1 = evaluate_policy(r1).decision_fingerprint
    fp2 = evaluate_policy(r2).decision_fingerprint
    assert fp1 == fp2


# --- freshness / review / publication ---


def test_hard_stale_runtime_deny():
    r = _req(
        freshness_status=FreshnessStatus.HARD_STALE,
        action=GovernanceAction.CITE_LINK,
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.HARD_STALE


def test_hard_stale_stage_for_review_quarantine():
    r = _req(
        action=GovernanceAction.STAGE_FOR_REVIEW,
        freshness_status=FreshnessStatus.HARD_STALE,
        review_status=ReviewStatus.QUARANTINED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STAGE_FOR_REVIEW,
                obligations=(),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.QUARANTINE
    assert result.primary_reason is PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW


def test_quarantined_retrieval_deny():
    r = _req(review_status=ReviewStatus.QUARANTINED)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.CONTENT_NOT_APPROVED


def test_pending_review_retrieval_deny():
    r = _req(review_status=ReviewStatus.PENDING_HUMAN)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.CONTENT_NOT_APPROVED


def test_approved_unpublished_deny():
    r = _req(publication_state=PublicationState.UNPUBLISHED)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.CONTENT_NOT_PUBLISHED


def test_approved_published_grant_allow():
    r = _req()
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT


def test_precedence_credential_before_feature_disabled():
    r = _req(
        credential_status=CredentialValidityStatus.REVOKED,
        feature_enabled=False,
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_REVOKED


def test_precedence_hard_stale_before_feature_disabled():
    r = _req(
        freshness_status=FreshnessStatus.HARD_STALE,
        feature_enabled=False,
        action=GovernanceAction.CITE_LINK,
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.HARD_STALE


# --- publish / stage ---


def test_publish_requires_human_review():
    r = _req(
        action=GovernanceAction.PUBLISH,
        grants=(
            _grant(
                action=GovernanceAction.PUBLISH,
                obligations=(PermissionObligation(ObligationKind.HUMAN_REVIEW, ()),),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED


def test_publish_extra_unsatisfied_obligation_denied():
    human = PermissionObligation(ObligationKind.HUMAN_REVIEW, ())
    attribution = PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),))
    r = _req(
        action=GovernanceAction.PUBLISH,
        grants=(
            _grant(
                action=GovernanceAction.PUBLISH,
                obligations=(human, attribution),
            ),
        ),
        fulfilled_obligations=(human,),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED


def test_publish_all_obligations_fulfilled_allow():
    human = PermissionObligation(ObligationKind.HUMAN_REVIEW, ())
    attribution = PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),))
    r = _req(
        action=GovernanceAction.PUBLISH,
        grants=(
            _grant(
                action=GovernanceAction.PUBLISH,
                obligations=(human, attribution),
            ),
        ),
        fulfilled_obligations=(human, attribution),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT


def test_automated_publish_deny():
    r = _req(
        action=GovernanceAction.PUBLISH,
        automated=True,
        grants=(
            _grant(
                action=GovernanceAction.PUBLISH,
                obligations=(
                    PermissionObligation(ObligationKind.HUMAN_REVIEW, ()),
                ),
            ),
        ),
        fulfilled_obligations=(PermissionObligation(ObligationKind.HUMAN_REVIEW, ()),),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.AUTOMATED_PUBLISH_FORBIDDEN


def test_stage_for_review_returns_quarantine():
    r = _req(
        action=GovernanceAction.STAGE_FOR_REVIEW,
        review_status=ReviewStatus.QUARANTINED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STAGE_FOR_REVIEW,
                obligations=(),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.QUARANTINE
    assert result.primary_reason is PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW


def test_stage_unsatisfied_obligation_quarantine_not_allow():
    r = _req(
        action=GovernanceAction.STAGE_FOR_REVIEW,
        review_status=ReviewStatus.QUARANTINED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STAGE_FOR_REVIEW,
                obligations=(PermissionObligation(ObligationKind.HUMAN_REVIEW, ()),),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.QUARANTINE
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED
    assert result.outcome is not PolicyOutcome.ALLOW


# --- verify-only / connector / automation ---


def test_point_lookup_verify_only():
    r = _req(
        action=GovernanceAction.POINT_LOOKUP,
        mode=EvaluationMode.VERIFY_ONLY,
        grants=(_grant(action=GovernanceAction.POINT_LOOKUP, obligations=()),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.VERIFY_ONLY


def test_point_lookup_unsatisfied_obligation_denied():
    r = _req(
        action=GovernanceAction.POINT_LOOKUP,
        grants=(
            _grant(
                action=GovernanceAction.POINT_LOOKUP,
                obligations=(PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),)),),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED


def test_point_lookup_fulfilled_obligations_allow():
    r = _req(
        action=GovernanceAction.POINT_LOOKUP,
        grants=(
            _grant(
                action=GovernanceAction.POINT_LOOKUP,
                obligations=(PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),)),),
            ),
        ),
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),)),
        ),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT


def test_verify_only_storage_deny():
    r = _req(
        action=GovernanceAction.STORE_RAW,
        mode=EvaluationMode.VERIFY_ONLY,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(
                    PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
                ),
            ),
        ),
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
        ),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.VERIFY_ONLY_ACTION_FORBIDDEN


def test_connector_disabled_fetch_deny():
    r = _req(
        action=GovernanceAction.FETCH,
        connector_enabled=False,
        grants=(_grant(action=GovernanceAction.FETCH),),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.CONNECTOR_DISABLED


def test_automation_disabled_fetch_deny():
    r = _req(
        action=GovernanceAction.FETCH,
        automated=True,
        automation_status=AutomationStatus.DISABLED,
        grants=(_grant(action=GovernanceAction.FETCH),),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.AUTOMATION_DISABLED


def test_scheduled_stage_fetch_allow():
    r = _req(
        action=GovernanceAction.FETCH,
        automated=True,
        automation_status=AutomationStatus.SCHEDULED_STAGE_ONLY,
        review_status=ReviewStatus.QUARANTINED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(_grant(action=GovernanceAction.FETCH, obligations=()),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW


def test_fetch_grant_does_not_allow_storage():
    r = _req(
        action=GovernanceAction.STORE_RAW,
        grants=(_grant(action=GovernanceAction.FETCH, obligations=()),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY


def test_storage_requires_retention():
    r = _req(
        action=GovernanceAction.STORE_RAW,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(
                    PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
                ),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED


def test_storage_wrong_retention_value_denied():
    r = _req(
        action=GovernanceAction.STORE_RAW,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(
                    PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
                ),
            ),
        ),
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "long"),)),
        ),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED


def test_storage_with_retention_allow():
    r = _req(
        action=GovernanceAction.STORE_RAW,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(
                    PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
                ),
            ),
        ),
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
        ),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW


def test_storage_extra_unsatisfied_obligation_denied():
    retention = PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),))
    attribution = PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),))
    r = _req(
        action=GovernanceAction.STORE_RAW,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(retention, attribution),
            ),
        ),
        fulfilled_obligations=(retention,),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED


def test_storage_all_obligations_fulfilled_allow():
    retention = PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),))
    attribution = PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),))
    r = _req(
        action=GovernanceAction.STORE_NORMALIZED,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_NORMALIZED,
                obligations=(retention, attribution),
            ),
        ),
        fulfilled_obligations=(retention, attribution),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT


def test_missing_obligation_deny():
    r = _req(fulfilled_obligations=())
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.OBLIGATION_UNSATISFIED


def test_fulfilled_obligations_order_permutation_invariant():
    ob_a = PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),))
    ob_b = PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),))
    r1 = _req(
        action=GovernanceAction.STORE_RAW,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(ob_b,),
            ),
        ),
        fulfilled_obligations=(ob_a, ob_b),
    )
    r2 = _req(
        action=GovernanceAction.STORE_RAW,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(ob_b,),
            ),
        ),
        fulfilled_obligations=(ob_b, ob_a),
    )
    res1 = evaluate_policy(r1)
    res2 = evaluate_policy(r2)
    assert res1.outcome is res2.outcome
    assert res1.decision_fingerprint == res2.decision_fingerprint


def test_obligation_parameter_order_equivalent():
    required = PermissionObligation(
        ObligationKind.RETENTION_CLASS,
        (("alpha", "1"), ("beta", "2")),
    )
    fulfilled_a = PermissionObligation(
        ObligationKind.RETENTION_CLASS,
        (("alpha", "1"), ("beta", "2")),
    )
    fulfilled_b = PermissionObligation(
        ObligationKind.RETENTION_CLASS,
        (("beta", "2"), ("alpha", "1")),
    )
    base = dict(
        action=GovernanceAction.STORE_RAW,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(required,),
            ),
        ),
    )
    r1 = _req(**base, fulfilled_obligations=(fulfilled_a,))
    r2 = _req(**base, fulfilled_obligations=(fulfilled_b,))
    res1 = evaluate_policy(r1)
    res2 = evaluate_policy(r2)
    assert res1.outcome is PolicyOutcome.ALLOW
    assert res2.outcome is PolicyOutcome.ALLOW
    assert res1.decision_fingerprint == res2.decision_fingerprint


def test_outage_blocks_refresh():
    r = _req(
        action=GovernanceAction.REFRESH,
        source_operational_status=SourceOperationalStatus.OUTAGE,
        grants=(_grant(action=GovernanceAction.REFRESH),),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.SOURCE_OUTAGE


def test_outage_blocks_point_lookup():
    r = _req(
        action=GovernanceAction.POINT_LOOKUP,
        source_operational_status=SourceOperationalStatus.OUTAGE,
        grants=(_grant(action=GovernanceAction.POINT_LOOKUP),),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.SOURCE_OUTAGE


def test_outage_does_not_revive_stale_runtime_cite_link():
    r = _req(
        source_operational_status=SourceOperationalStatus.OUTAGE,
        freshness_status=FreshnessStatus.HARD_STALE,
        action=GovernanceAction.CITE_LINK,
        grants=(_grant(action=GovernanceAction.CITE_LINK, obligations=()),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.HARD_STALE


def test_feature_disabled_deny():
    r = _req(feature_enabled=False)
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.FEATURE_DISABLED


# --- fingerprint ---


def test_fingerprint_stable():
    r = _req()
    a = evaluate_policy(r)
    b = evaluate_policy(r)
    assert a.decision_fingerprint == b.decision_fingerprint
    assert len(a.decision_fingerprint) == 64
    assert a.decision_fingerprint == a.decision_fingerprint.lower()


def test_fingerprint_primary_reason_changes_hash():
    r = _req()
    matched = r.grants
    same_set_a = (
        PolicyReasonCode.HARD_STALE,
        PolicyReasonCode.FEATURE_DISABLED,
    )
    same_set_b = (
        PolicyReasonCode.FEATURE_DISABLED,
        PolicyReasonCode.HARD_STALE,
    )
    fp_a = _decision_fingerprint(r, PolicyOutcome.DENY, same_set_a, matched)
    fp_b = _decision_fingerprint(r, PolicyOutcome.DENY, same_set_b, matched)
    assert same_set_a[0] is not same_set_b[0]
    assert sorted(c.value for c in same_set_a) == sorted(c.value for c in same_set_b)
    assert fp_a != fp_b
    assert fp_a == fp_a.lower() and len(fp_a) == 64


def test_fingerprint_secondary_reason_permutation_stable():
    r = _req()
    matched = r.grants
    primary = PolicyReasonCode.HARD_STALE
    order_a = (
        primary,
        PolicyReasonCode.FEATURE_DISABLED,
        PolicyReasonCode.EXPLICIT_DENY,
    )
    order_b = (
        primary,
        PolicyReasonCode.EXPLICIT_DENY,
        PolicyReasonCode.FEATURE_DISABLED,
    )
    fp_a = _decision_fingerprint(r, PolicyOutcome.DENY, order_a, matched)
    fp_b = _decision_fingerprint(r, PolicyOutcome.DENY, order_b, matched)
    assert fp_a == fp_b


def test_primary_reason_always_first_in_reason_codes():
    r = _req(credential_status=CredentialValidityStatus.REVOKED, feature_enabled=False)
    result = evaluate_policy(r)
    assert result.reason_codes[0] is result.primary_reason
    assert result.primary_reason is PolicyReasonCode.CREDENTIAL_REVOKED


def test_material_input_changes_fingerprint():
    r1 = _req()
    r2 = _req(action=GovernanceAction.DISPLAY_FIELDS)
    fp1 = evaluate_policy(r1).decision_fingerprint
    fp2 = evaluate_policy(r2).decision_fingerprint
    assert fp1 != fp2


def test_obligation_value_change_changes_fingerprint():
    base = dict(
        action=GovernanceAction.STORE_RAW,
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant(
                action=GovernanceAction.STORE_RAW,
                obligations=(
                    PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
                ),
            ),
        ),
    )
    r1 = _req(
        **base,
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
        ),
    )
    r2 = _req(
        **base,
        fulfilled_obligations=(
            PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "long"),)),
        ),
    )
    fp1 = evaluate_policy(r1).decision_fingerprint
    fp2 = evaluate_policy(r2).decision_fingerprint
    assert fp1 != fp2


def test_fingerprint_excludes_secret_evidence_values():
    secret = "top-secret-evidence-token-9f3a2b1c"
    grant = _grant(evidence_ids=(secret,))
    r = _req(grants=(grant,))
    result = evaluate_policy(r)
    assert secret not in result.decision_fingerprint
    payload_fp = _decision_fingerprint(
        r,
        result.outcome,
        result.reason_codes,
        (grant,),
    )
    assert secret not in payload_fp


def test_deterministic_reason_ordering():
    r = _req()
    result = evaluate_policy(r)
    assert result.reason_codes[0] is result.primary_reason
    assert len(result.reason_codes) == len(set(result.reason_codes))
    if len(result.reason_codes) > 1:
        secondary = result.reason_codes[1:]
        assert secondary == tuple(sorted(secondary, key=lambda c: c.value))


def test_algorithm_version_constant():
    assert EVALUATOR_ALGORITHM_VERSION == "sedi.governance.policy_evaluator.v1"


# --- import hygiene ---


def test_no_db_application_imports():
    mod_path = Path(inspect.getfile(evaluate_policy))
    source = mod_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {"hashlib", "json", "dataclasses", "datetime", "enum", "typing", "__future__", "backend"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed or alias.name.startswith("backend.app.services.governance.contracts"), alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert mod.startswith("backend.app.services.governance.contracts") or mod in {
                "__future__",
                "dataclasses",
                "datetime",
                "enum",
                "typing",
                "hashlib",
                "json",
            }, mod
    forbidden = (
        "EvidenceUseAssessment",
        "KnowledgeRequirement",
        "KnowledgePackGovernanceState",
        "PredictionUseBoundary",
        "GovernedAuthorityKind",
        "AuthorityUseCase",
        "ClinicalJurisdiction",
        "ExternalTaxonomyMapping",
    )
    for symbol in forbidden:
        assert symbol not in source
    assert "sqlalchemy" not in source.lower()
    assert "openai" not in source.lower()
    assert "datetime.now" not in source
    assert "uuid" not in source.lower()
    assert "random" not in source.lower()


# --- A2-R1 sensitivity matching ---


def _grant_for_sensitivity(action, sensitivity, **overrides):
    params = {
        "action": action,
        "scope": _scope(data_sensitivity=sensitivity),
        "obligations": (),
    }
    params.update(overrides)
    return _grant(**params)


def test_public_grant_public_request_allow():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PUBLIC_EDUCATIONAL),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT


@pytest.mark.parametrize(
    "request_sensitivity",
    [
        DataSensitivity.PROFESSIONAL_DIRECTORY,
        DataSensitivity.CONTACT_PII,
        DataSensitivity.HEALTH_ADVICE,
    ],
)
def test_public_grant_cannot_authorize_higher_sensitivity(request_sensitivity):
    r = _req(
        scope=_scope(data_sensitivity=request_sensitivity),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PUBLIC_EDUCATIONAL),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


@pytest.mark.parametrize(
    "request_sensitivity",
    [DataSensitivity.CONTACT_PII, DataSensitivity.HEALTH_ADVICE],
)
def test_professional_directory_cannot_authorize_higher_sensitivity(request_sensitivity):
    r = _req(
        scope=_scope(data_sensitivity=request_sensitivity),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PROFESSIONAL_DIRECTORY),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_contact_pii_cannot_authorize_health_advice():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.CONTACT_PII),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_health_advice_cannot_authorize_contact_pii():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.CONTACT_PII),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.HEALTH_ADVICE),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_unknown_restricted_request_fails_closed():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.UNKNOWN_RESTRICTED),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PUBLIC_EDUCATIONAL),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.UNKNOWN_DATA_SENSITIVITY


def test_unknown_restricted_grant_cannot_authorize_known_sensitivity():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.UNKNOWN_RESTRICTED),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.UNKNOWN_DATA_SENSITIVITY


def test_unknown_restricted_exact_match_still_denied():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.UNKNOWN_RESTRICTED),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.UNKNOWN_RESTRICTED),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.UNKNOWN_DATA_SENSITIVITY


def test_sensitivity_mismatch_applies_to_display_fields():
    r = _req(
        action=GovernanceAction.DISPLAY_FIELDS,
        scope=_scope(data_sensitivity=DataSensitivity.CONTACT_PII, field_names=("phone",)),
        grants=(
            _grant_for_sensitivity(
                GovernanceAction.DISPLAY_FIELDS,
                DataSensitivity.PUBLIC_EDUCATIONAL,
                scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL, field_names=("phone",)),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_sensitivity_mismatch_applies_to_point_lookup():
    r = _req(
        action=GovernanceAction.POINT_LOOKUP,
        scope=_scope(data_sensitivity=DataSensitivity.CONTACT_PII),
        grants=(_grant_for_sensitivity(GovernanceAction.POINT_LOOKUP, DataSensitivity.PUBLIC_EDUCATIONAL),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_sensitivity_mismatch_applies_to_storage():
    retention = PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),))
    r = _req(
        action=GovernanceAction.STORE_RAW,
        scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE),
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.UNPUBLISHED,
        grants=(
            _grant_for_sensitivity(
                GovernanceAction.STORE_RAW,
                DataSensitivity.PUBLIC_EDUCATIONAL,
                obligations=(retention,),
            ),
        ),
        fulfilled_obligations=(retention,),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_sensitivity_mismatch_applies_to_connector_runtime():
    r = _req(
        action=GovernanceAction.FETCH,
        scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE),
        grants=(_grant_for_sensitivity(GovernanceAction.FETCH, DataSensitivity.PUBLIC_EDUCATIONAL),),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_matching_scope_dimension_cannot_bypass_sensitivity():
    g = _grant(
        action=GovernanceAction.CITE_LINK,
        scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
        obligations=(),
    )
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE),
        grants=(g,),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.DATA_SENSITIVITY_MISMATCH


def test_multiple_grants_one_matching_sensitivity_still_allows():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE),
        grants=(
            _grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PUBLIC_EDUCATIONAL, grant_id="g-bad"),
            _grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.HEALTH_ADVICE, grant_id="g-good"),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW


def test_sensitivity_grant_order_invariant():
    g_good = _grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.HEALTH_ADVICE, grant_id="g-good")
    g_bad = _grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PUBLIC_EDUCATIONAL, grant_id="g-bad")
    r1 = _req(scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE), grants=(g_good, g_bad), fulfilled_obligations=())
    r2 = _req(scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE), grants=(g_bad, g_good), fulfilled_obligations=())
    res1 = evaluate_policy(r1)
    res2 = evaluate_policy(r2)
    assert res1.outcome is PolicyOutcome.ALLOW
    assert res2.outcome is PolicyOutcome.ALLOW
    assert res1.primary_reason is res2.primary_reason


def test_sensitivity_explicit_deny_precedence():
    r = _req(
        scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
        grants=(
            _grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PUBLIC_EDUCATIONAL),
            _grant(
                grant_id="g-deny",
                decision=PermissionDecision.DENY_EXPLICIT,
                scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
            ),
        ),
        fulfilled_obligations=(),
    )
    result = evaluate_policy(r)
    assert result.primary_reason is PolicyReasonCode.EXPLICIT_DENY


def test_sensitivity_fingerprint_changes_with_mismatch():
    r1 = _req(
        scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.PUBLIC_EDUCATIONAL),),
        fulfilled_obligations=(),
    )
    r2 = _req(
        scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE),
        grants=(_grant_for_sensitivity(GovernanceAction.CITE_LINK, DataSensitivity.HEALTH_ADVICE),),
        fulfilled_obligations=(),
    )
    assert evaluate_policy(r1).decision_fingerprint != evaluate_policy(r2).decision_fingerprint


# --- A2-R1 freshness matrix ---


_ALL_ACTIONS = tuple(GovernanceAction)
_ACTIONS_THAT_CAN_ALLOW = tuple(
    action for action in GovernanceAction if action is not GovernanceAction.STAGE_FOR_REVIEW
)


def _action_ready_req(action: GovernanceAction, freshness: FreshnessStatus = FreshnessStatus.FRESH, **overrides):
    retention = PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),))
    human = PermissionObligation(ObligationKind.HUMAN_REVIEW, ())
    base = dict(
        action=action,
        freshness_status=freshness,
        fulfilled_obligations=(),
    )
    if action in {GovernanceAction.STORE_RAW, GovernanceAction.STORE_NORMALIZED}:
        base["grants"] = (_grant(action=action, obligations=(retention,)),)
        base["fulfilled_obligations"] = (retention,)
        base["review_status"] = ReviewStatus.APPROVED
        base["publication_state"] = PublicationState.UNPUBLISHED
    elif action is GovernanceAction.PUBLISH:
        base["grants"] = (_grant(action=action, obligations=(human,)),)
        base["fulfilled_obligations"] = (human,)
    elif action is GovernanceAction.STAGE_FOR_REVIEW:
        base["grants"] = (_grant(action=action, obligations=()),)
        base["review_status"] = ReviewStatus.QUARANTINED
        base["publication_state"] = PublicationState.UNPUBLISHED
    elif action is GovernanceAction.DISPLAY_FIELDS:
        base["scope"] = _scope(field_names=("title",))
        base["grants"] = (
            _grant(action=action, scope=_scope(field_names=("title",)), obligations=()),
        )
    else:
        base["grants"] = (_grant(action=action, obligations=()),)
    base.update(overrides)
    return _req(**base)


@pytest.mark.parametrize("action", _ACTIONS_THAT_CAN_ALLOW)
def test_fresh_action_can_reach_allow_when_other_gates_pass(action):
    r = _action_ready_req(action, FreshnessStatus.FRESH)
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.ALLOW


def test_stage_for_review_soft_stale_quarantine():
    r = _action_ready_req(GovernanceAction.STAGE_FOR_REVIEW, FreshnessStatus.SOFT_STALE)
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.QUARANTINE
    assert result.primary_reason is PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW


def test_stage_for_review_unknown_age_quarantine():
    r = _action_ready_req(GovernanceAction.STAGE_FOR_REVIEW, FreshnessStatus.UNKNOWN_AGE)
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.QUARANTINE
    assert result.primary_reason is PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW


@pytest.mark.parametrize("action", _ALL_ACTIONS)
def test_soft_stale_never_allows(action):
    if action is GovernanceAction.STAGE_FOR_REVIEW:
        r = _action_ready_req(action, FreshnessStatus.SOFT_STALE)
        result = evaluate_policy(r)
        assert result.outcome is PolicyOutcome.QUARANTINE
        assert result.primary_reason is PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW
        return
    r = _action_ready_req(action, FreshnessStatus.SOFT_STALE)
    result = evaluate_policy(r)
    assert result.outcome is not PolicyOutcome.ALLOW
    if action is GovernanceAction.POINT_LOOKUP and r.mode is EvaluationMode.VERIFY_ONLY:
        assert result.outcome is PolicyOutcome.VERIFY_ONLY
    else:
        assert result.outcome is PolicyOutcome.DENY
        assert result.primary_reason is PolicyReasonCode.SOFT_STALE_REQUIRES_REVIEW


@pytest.mark.parametrize("action", _ALL_ACTIONS)
def test_unknown_age_never_allows(action):
    if action is GovernanceAction.STAGE_FOR_REVIEW:
        r = _action_ready_req(action, FreshnessStatus.UNKNOWN_AGE)
        result = evaluate_policy(r)
        assert result.outcome is PolicyOutcome.QUARANTINE
        assert result.primary_reason is PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW
        return
    r = _action_ready_req(action, FreshnessStatus.UNKNOWN_AGE)
    result = evaluate_policy(r)
    assert result.outcome is not PolicyOutcome.ALLOW
    if action is GovernanceAction.POINT_LOOKUP and r.mode is EvaluationMode.VERIFY_ONLY:
        assert result.outcome is PolicyOutcome.VERIFY_ONLY
    else:
        assert result.outcome is PolicyOutcome.DENY
        assert result.primary_reason is PolicyReasonCode.UNKNOWN_AGE_DENIED


@pytest.mark.parametrize("action", _ALL_ACTIONS)
def test_hard_stale_never_allows(action):
    if action is GovernanceAction.STAGE_FOR_REVIEW:
        r = _action_ready_req(action, FreshnessStatus.HARD_STALE)
        result = evaluate_policy(r)
        assert result.outcome is PolicyOutcome.QUARANTINE
        assert result.primary_reason is PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW
        return
    r = _action_ready_req(action, FreshnessStatus.HARD_STALE)
    result = evaluate_policy(r)
    assert result.outcome is not PolicyOutcome.ALLOW
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.HARD_STALE


def test_verify_only_soft_stale_is_non_allow():
    r = _action_ready_req(
        GovernanceAction.POINT_LOOKUP,
        FreshnessStatus.SOFT_STALE,
        mode=EvaluationMode.VERIFY_ONLY,
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.VERIFY_ONLY
    assert result.primary_reason is PolicyReasonCode.VERIFY_ONLY_REQUIRED


def test_verify_only_unknown_age_is_non_allow():
    r = _action_ready_req(
        GovernanceAction.POINT_LOOKUP,
        FreshnessStatus.UNKNOWN_AGE,
        mode=EvaluationMode.VERIFY_ONLY,
    )
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.VERIFY_ONLY
    assert result.primary_reason is PolicyReasonCode.VERIFY_ONLY_REQUIRED


def test_valid_grant_cannot_bypass_soft_stale():
    r = _action_ready_req(GovernanceAction.CITE_LINK, FreshnessStatus.SOFT_STALE)
    result = evaluate_policy(r)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.SOFT_STALE_REQUIRES_REVIEW


def test_freshness_result_invariant_under_grant_order():
    g_a = _grant(grant_id="g-a", obligations=())
    g_b = _grant(grant_id="g-b", obligations=())
    r1 = _req(
        freshness_status=FreshnessStatus.SOFT_STALE,
        grants=(g_a, g_b),
        fulfilled_obligations=(),
    )
    r2 = _req(
        freshness_status=FreshnessStatus.SOFT_STALE,
        grants=(g_b, g_a),
        fulfilled_obligations=(),
    )
    res1 = evaluate_policy(r1)
    res2 = evaluate_policy(r2)
    assert res1.primary_reason is res2.primary_reason
    assert res1.outcome is res2.outcome


def test_unrelated_unknown_restricted_allow_does_not_poison_valid_exact_allow():
    valid_allow = _grant_for_sensitivity(
        GovernanceAction.CITE_LINK,
        DataSensitivity.PUBLIC_EDUCATIONAL,
        grant_id="g-public-allow",
    )
    unknown_allow = _grant_for_sensitivity(
        GovernanceAction.CITE_LINK,
        DataSensitivity.UNKNOWN_RESTRICTED,
        grant_id="g-unknown-allow",
    )
    request_scope = _scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL)
    first = evaluate_policy(
        _req(
            scope=request_scope,
            grants=(valid_allow, unknown_allow),
            fulfilled_obligations=(),
        )
    )
    second = evaluate_policy(
        _req(
            scope=request_scope,
            grants=(unknown_allow, valid_allow),
            fulfilled_obligations=(),
        )
    )
    assert first.outcome is PolicyOutcome.ALLOW
    assert first.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT
    assert first.reason_codes == (PolicyReasonCode.ALLOW_EXPLICIT,)
    assert second.outcome is PolicyOutcome.ALLOW
    assert second.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT
    assert second.reason_codes == (PolicyReasonCode.ALLOW_EXPLICIT,)
    assert first.decision_fingerprint == second.decision_fingerprint


def test_unrelated_unknown_restricted_deny_does_not_block_valid_exact_allow():
    valid_allow = _grant_for_sensitivity(
        GovernanceAction.CITE_LINK,
        DataSensitivity.PUBLIC_EDUCATIONAL,
        grant_id="g-public-allow",
    )
    unknown_deny = _grant_for_sensitivity(
        GovernanceAction.CITE_LINK,
        DataSensitivity.UNKNOWN_RESTRICTED,
        grant_id="g-unknown-deny",
        decision=PermissionDecision.DENY_EXPLICIT,
    )
    request_scope = _scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL)
    first = evaluate_policy(
        _req(
            scope=request_scope,
            grants=(valid_allow, unknown_deny),
            fulfilled_obligations=(),
        )
    )
    second = evaluate_policy(
        _req(
            scope=request_scope,
            grants=(unknown_deny, valid_allow),
            fulfilled_obligations=(),
        )
    )
    assert first.outcome is PolicyOutcome.ALLOW
    assert first.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT
    assert first.reason_codes == (PolicyReasonCode.ALLOW_EXPLICIT,)
    assert PolicyReasonCode.EXPLICIT_DENY not in first.reason_codes
    assert second.outcome is PolicyOutcome.ALLOW
    assert second.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT
    assert second.reason_codes == (PolicyReasonCode.ALLOW_EXPLICIT,)
    assert PolicyReasonCode.EXPLICIT_DENY not in second.reason_codes
    assert first.decision_fingerprint == second.decision_fingerprint


def test_cross_sensitivity_explicit_deny_does_not_override_matching_allow():
    public_result = evaluate_policy(
        _req(
            scope=_scope(data_sensitivity=DataSensitivity.PUBLIC_EDUCATIONAL),
            grants=(
                _grant_for_sensitivity(
                    GovernanceAction.CITE_LINK,
                    DataSensitivity.PUBLIC_EDUCATIONAL,
                    grant_id="g-public-allow",
                ),
                _grant_for_sensitivity(
                    GovernanceAction.CITE_LINK,
                    DataSensitivity.HEALTH_ADVICE,
                    grant_id="g-health-deny",
                    decision=PermissionDecision.DENY_EXPLICIT,
                ),
            ),
            fulfilled_obligations=(),
        )
    )
    health_result = evaluate_policy(
        _req(
            scope=_scope(data_sensitivity=DataSensitivity.HEALTH_ADVICE),
            grants=(
                _grant_for_sensitivity(
                    GovernanceAction.CITE_LINK,
                    DataSensitivity.HEALTH_ADVICE,
                    grant_id="g-health-allow",
                ),
                _grant_for_sensitivity(
                    GovernanceAction.CITE_LINK,
                    DataSensitivity.PUBLIC_EDUCATIONAL,
                    grant_id="g-public-deny",
                    decision=PermissionDecision.DENY_EXPLICIT,
                ),
            ),
            fulfilled_obligations=(),
        )
    )
    assert public_result.outcome is PolicyOutcome.ALLOW
    assert public_result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT
    assert public_result.reason_codes == (PolicyReasonCode.ALLOW_EXPLICIT,)
    assert PolicyReasonCode.EXPLICIT_DENY not in public_result.reason_codes
    assert PolicyReasonCode.DATA_SENSITIVITY_MISMATCH not in public_result.reason_codes
    assert health_result.outcome is PolicyOutcome.ALLOW
    assert health_result.primary_reason is PolicyReasonCode.ALLOW_EXPLICIT
    assert health_result.reason_codes == (PolicyReasonCode.ALLOW_EXPLICIT,)
    assert PolicyReasonCode.EXPLICIT_DENY not in health_result.reason_codes
    assert PolicyReasonCode.DATA_SENSITIVITY_MISMATCH not in health_result.reason_codes


def test_verify_only_point_lookup_hard_stale_is_denied():
    result = evaluate_policy(
        _action_ready_req(
            GovernanceAction.POINT_LOOKUP,
            FreshnessStatus.HARD_STALE,
            mode=EvaluationMode.VERIFY_ONLY,
        )
    )
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.HARD_STALE
    assert result.reason_codes == (PolicyReasonCode.HARD_STALE,)
    assert result.outcome is not PolicyOutcome.VERIFY_ONLY
    assert result.outcome is not PolicyOutcome.ALLOW


def test_malformed_freshness_fails_closed_and_never_allows():
    request = _action_ready_req(
        GovernanceAction.CITE_LINK,
        "malformed",  # type: ignore[arg-type]
    )
    result = evaluate_policy(request)
    assert result.outcome is PolicyOutcome.DENY
    assert result.primary_reason is PolicyReasonCode.INVALID_REQUEST
    assert result.reason_codes == (PolicyReasonCode.INVALID_REQUEST,)
    assert result.outcome is not PolicyOutcome.VERIFY_ONLY
    assert result.outcome is not PolicyOutcome.ALLOW


# --- A2-R1 composition boundary ---


def test_policy_outcome_allow_is_not_required_found():
    from backend.app.services.governance.contracts import KnowledgePolicyDecision

    assert PolicyOutcome.ALLOW is not KnowledgePolicyDecision.REQUIRED_FOUND


def test_policy_outcome_allow_is_not_evidence_use_allow():
    from backend.app.services.governance.contracts import EvidenceUseDecision

    assert PolicyOutcome.ALLOW is not EvidenceUseDecision.ALLOW_WITH_CITATION
    assert PolicyOutcome.ALLOW is not EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS


def test_policy_evaluation_result_outcome_type_is_policy_outcome():
    result = evaluate_policy(_req())
    assert isinstance(result.outcome, PolicyOutcome)


def test_module_docstring_states_generic_only_authority():
    mod_path = Path(inspect.getfile(evaluate_policy))
    source = mod_path.read_text(encoding="utf-8")
    assert "not" in source.lower()
    assert "EvidenceUseDecision.ALLOW_WITH_CITATION" in source
    assert "KnowledgePolicyDecision.REQUIRED_FOUND" in source


def test_result_docstring_states_generic_only_authority():
    source = inspect.getsource(PolicyEvaluationResult)
    assert "PolicyOutcome" in source
    assert "generic" in source.lower()
