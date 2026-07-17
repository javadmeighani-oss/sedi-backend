"""Section 15-I5-A2 — pure deterministic generic action-permission evaluator.

This module evaluates generic ``GovernanceAction`` permission against
``ScopedPermissionGrant`` inputs only. ``PolicyOutcome.ALLOW`` means the
generic action-permission checks represented here passed. It is **not**
``EvidenceUseDecision.ALLOW_WITH_CITATION``, **not**
``EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS``, **not**
``KnowledgePolicyDecision.REQUIRED_FOUND``, and **not** provider/facility
verification or prediction authorization. Clinical evidence use still
requires an explicit fail-closed composition adapter with the A1-R1
authorities (not implemented here).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence, Tuple

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

EVALUATOR_ALGORITHM_VERSION = "sedi.governance.policy_evaluator.v1"

_INVALID_FRESHNESS_STATUS_SENTINEL = "__INVALID_FRESHNESS_STATUS__"

_RUNTIME_ACTIONS = frozenset(
    {
        GovernanceAction.DERIVE,
        GovernanceAction.INDEX_EMBED,
        GovernanceAction.CITE_LINK,
        GovernanceAction.DISPLAY_FIELDS,
    }
)

_HARD_STALE_DENY_ACTIONS = _RUNTIME_ACTIONS | frozenset(
    {
        GovernanceAction.PUBLISH,
        GovernanceAction.POINT_LOOKUP,
    }
)

_CONNECTOR_ACTIONS = frozenset(
    {
        GovernanceAction.FETCH,
        GovernanceAction.REFRESH,
        GovernanceAction.POINT_LOOKUP,
    }
)

_STORAGE_ACTIONS = frozenset(
    {
        GovernanceAction.STORE_RAW,
        GovernanceAction.STORE_NORMALIZED,
    }
)

_CREDENTIAL_SENSITIVITIES = frozenset(
    {
        DataSensitivity.PROFESSIONAL_DIRECTORY,
        DataSensitivity.CONTACT_PII,
    }
)

_CREDENTIAL_BEARING_ACTIONS = frozenset(
    {
        GovernanceAction.POINT_LOOKUP,
        GovernanceAction.DISPLAY_FIELDS,
    }
)


class PolicyReasonCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    SOURCE_DISABLED = "source_disabled"
    SOURCE_SUSPENDED = "source_suspended"
    SOURCE_OUTAGE = "source_outage"
    CREDENTIAL_UNVERIFIED = "credential_unverified"
    CREDENTIAL_SUSPENDED = "credential_suspended"
    CREDENTIAL_REVOKED = "credential_revoked"
    CREDENTIAL_EXPIRED = "credential_expired"
    LICENSE_UNKNOWN = "license_unknown"
    LICENSE_EXPIRED = "license_expired"
    LICENSE_CONFLICT = "license_conflict"
    EXPLICIT_DENY = "explicit_deny"
    POLICY_CONFLICT = "policy_conflict"
    NO_MATCHING_GRANT = "no_matching_grant"
    GRANT_EXPIRED = "grant_expired"
    SCOPE_MISMATCH = "scope_mismatch"
    FIELD_SCOPE_NOT_COVERED = "field_scope_not_covered"
    DATA_SENSITIVITY_MISMATCH = "data_sensitivity_mismatch"
    UNKNOWN_DATA_SENSITIVITY = "unknown_data_sensitivity"
    HARD_STALE = "hard_stale"
    SOFT_STALE_REQUIRES_REVIEW = "soft_stale_requires_review"
    UNKNOWN_AGE_DENIED = "unknown_age_denied"
    CONTENT_NOT_APPROVED = "content_not_approved"
    CONTENT_NOT_PUBLISHED = "content_not_published"
    FEATURE_DISABLED = "feature_disabled"
    CONNECTOR_DISABLED = "connector_disabled"
    AUTOMATION_DISABLED = "automation_disabled"
    OBLIGATION_UNSATISFIED = "obligation_unsatisfied"
    VERIFY_ONLY_REQUIRED = "verify_only_required"
    VERIFY_ONLY_ACTION_FORBIDDEN = "verify_only_action_forbidden"
    STAGED_FOR_HUMAN_REVIEW = "staged_for_human_review"
    AUTOMATED_PUBLISH_FORBIDDEN = "automated_publish_forbidden"
    ALLOW_EXPLICIT = "allow_explicit"


class EvaluationMode(str, Enum):
    STANDARD = "standard"
    VERIFY_ONLY = "verify_only"


@dataclass(frozen=True)
class PolicyEvaluationRequest:
    """Generic action-permission request; not a clinical evidence-use request."""

    policy_version_id: str
    scope: PermissionScope
    action: GovernanceAction
    evaluation_at: datetime
    license_status: LicenseStatus
    source_operational_status: SourceOperationalStatus
    credential_status: CredentialValidityStatus
    freshness_status: FreshnessStatus
    review_status: ReviewStatus
    publication_state: PublicationState
    automation_status: AutomationStatus
    grants: Tuple[ScopedPermissionGrant, ...]
    fulfilled_obligations: Tuple[PermissionObligation, ...]
    feature_enabled: bool
    connector_enabled: bool
    automated: bool
    mode: EvaluationMode = EvaluationMode.STANDARD

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version_id, str) or not self.policy_version_id.strip():
            raise ValueError("policy_version_id_required")
        if not isinstance(self.evaluation_at, datetime):
            raise ValueError("evaluation_at_must_be_datetime")
        if self.evaluation_at.tzinfo is None or self.evaluation_at.tzinfo.utcoffset(self.evaluation_at) is None:
            raise ValueError("evaluation_at_must_be_timezone_aware")
        _assert_unique_grants(self.grants)
        _assert_unique_obligations(self.fulfilled_obligations)


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Generic action-permission result using ``PolicyOutcome`` only."""

    outcome: PolicyOutcome
    primary_reason: PolicyReasonCode
    reason_codes: Tuple[PolicyReasonCode, ...]
    matched_grant_ids: Tuple[str, ...]
    required_obligations: Tuple[PermissionObligation, ...]
    policy_version_id: str
    decision_fingerprint: str

    def __post_init__(self) -> None:
        if self.primary_reason not in self.reason_codes:
            raise ValueError("primary_reason_not_in_reason_codes")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes_duplicate")
        if len(self.matched_grant_ids) != len(set(self.matched_grant_ids)):
            raise ValueError("matched_grant_ids_duplicate")
        if list(self.matched_grant_ids) != sorted(self.matched_grant_ids):
            raise ValueError("matched_grant_ids_not_sorted")
        if not _is_sha256_hex(self.decision_fingerprint):
            raise ValueError("decision_fingerprint_invalid_sha256")


def evaluate_policy(request: PolicyEvaluationRequest) -> PolicyEvaluationResult:
    """Evaluate one governed generic action deterministically; exactly one outcome."""
    reasons: list[PolicyReasonCode] = []
    matched: list[ScopedPermissionGrant] = []

    def deny(code: PolicyReasonCode) -> PolicyEvaluationResult:
        return _finalize(request, PolicyOutcome.DENY, _with_primary(code, reasons), matched)

    def quarantine(code: PolicyReasonCode) -> PolicyEvaluationResult:
        return _finalize(request, PolicyOutcome.QUARANTINE, _with_primary(code, reasons), matched)

    def verify_only(code: PolicyReasonCode) -> PolicyEvaluationResult:
        freshness_block = _freshness_blocks_verify_only(request, matched, reasons)
        if freshness_block is not None:
            return freshness_block
        return _finalize(request, PolicyOutcome.VERIFY_ONLY, _with_primary(code, reasons), matched)

    def allow(code: PolicyReasonCode) -> PolicyEvaluationResult:
        freshness_block = _freshness_blocks_allow(request, matched, reasons)
        if freshness_block is not None:
            return freshness_block
        return _finalize(request, PolicyOutcome.ALLOW, _with_primary(code, reasons), matched)

    # 1) invalid request
    if not request.policy_version_id.strip():
        reasons.append(PolicyReasonCode.INVALID_REQUEST)
        return deny(PolicyReasonCode.INVALID_REQUEST)
    if not _is_valid_freshness_status(request.freshness_status):
        reasons.append(PolicyReasonCode.INVALID_REQUEST)
        return deny(PolicyReasonCode.INVALID_REQUEST)

    # 2) credential validity
    if request.credential_status is CredentialValidityStatus.REVOKED:
        reasons.append(PolicyReasonCode.CREDENTIAL_REVOKED)
        return deny(PolicyReasonCode.CREDENTIAL_REVOKED)
    if request.credential_status is CredentialValidityStatus.SUSPENDED:
        reasons.append(PolicyReasonCode.CREDENTIAL_SUSPENDED)
        return deny(PolicyReasonCode.CREDENTIAL_SUSPENDED)
    if request.credential_status is CredentialValidityStatus.EXPIRED:
        reasons.append(PolicyReasonCode.CREDENTIAL_EXPIRED)
        return deny(PolicyReasonCode.CREDENTIAL_EXPIRED)
    if request.credential_status in {
        CredentialValidityStatus.UNVERIFIED,
        CredentialValidityStatus.UNKNOWN,
    } and _requires_verified_credential(request):
        reasons.append(PolicyReasonCode.CREDENTIAL_UNVERIFIED)
        return deny(PolicyReasonCode.CREDENTIAL_UNVERIFIED)

    # 3) source suspended / general source blockers
    if request.source_operational_status is SourceOperationalStatus.SUSPENDED:
        reasons.append(PolicyReasonCode.SOURCE_SUSPENDED)
        return deny(PolicyReasonCode.SOURCE_SUSPENDED)
    if request.source_operational_status is SourceOperationalStatus.OUTAGE:
        if request.action in _CONNECTOR_ACTIONS:
            reasons.append(PolicyReasonCode.SOURCE_OUTAGE)
            return deny(PolicyReasonCode.SOURCE_OUTAGE)
    if request.source_operational_status is SourceOperationalStatus.DISABLED:
        if request.automated and request.action in _CONNECTOR_ACTIONS:
            reasons.append(PolicyReasonCode.SOURCE_DISABLED)
            return deny(PolicyReasonCode.SOURCE_DISABLED)

    # 4) license fail-closed
    if request.license_status is LicenseStatus.UNKNOWN:
        reasons.append(PolicyReasonCode.LICENSE_UNKNOWN)
        return deny(PolicyReasonCode.LICENSE_UNKNOWN)
    if request.license_status is LicenseStatus.EXPIRED:
        reasons.append(PolicyReasonCode.LICENSE_EXPIRED)
        return deny(PolicyReasonCode.LICENSE_EXPIRED)
    if request.license_status is LicenseStatus.CONFLICT:
        reasons.append(PolicyReasonCode.LICENSE_CONFLICT)
        return deny(PolicyReasonCode.LICENSE_CONFLICT)

    # 5) unknown sensitivity fail-closed before grant allow paths
    if request.scope.data_sensitivity is DataSensitivity.UNKNOWN_RESTRICTED:
        reasons.append(PolicyReasonCode.UNKNOWN_DATA_SENSITIVITY)
        return deny(PolicyReasonCode.UNKNOWN_DATA_SENSITIVITY)

    # 6) scoped grant resolution with mandatory sensitivity matching
    structural_matches = _structurally_matching_grants(request)
    sensitivity_matches = _sensitivity_matching_grants(request, structural_matches)

    expired = [g for g in sensitivity_matches if _grant_expired(g, request.evaluation_at)]
    active = [g for g in sensitivity_matches if _grant_in_validity_window(g, request.evaluation_at)]

    if expired and not active:
        reasons.append(PolicyReasonCode.GRANT_EXPIRED)
        return deny(PolicyReasonCode.GRANT_EXPIRED)

    conflicts = [g for g in active if g.decision is PermissionDecision.POLICY_CONFLICT]
    if conflicts:
        reasons.append(PolicyReasonCode.POLICY_CONFLICT)
        return deny(PolicyReasonCode.POLICY_CONFLICT)

    denies = [g for g in active if g.decision is PermissionDecision.DENY_EXPLICIT]
    if denies:
        if request.action is GovernanceAction.DISPLAY_FIELDS:
            if _field_denied(request, denies):
                reasons.append(PolicyReasonCode.EXPLICIT_DENY)
                return deny(PolicyReasonCode.EXPLICIT_DENY)
        else:
            reasons.append(PolicyReasonCode.EXPLICIT_DENY)
            return deny(PolicyReasonCode.EXPLICIT_DENY)

    allows = [g for g in active if g.decision is PermissionDecision.ALLOW_EXPLICIT]
    if not allows:
        if not structural_matches:
            reasons.append(PolicyReasonCode.NO_MATCHING_GRANT)
            return deny(PolicyReasonCode.NO_MATCHING_GRANT)
        if _has_unknown_restricted_grant(structural_matches):
            reasons.append(PolicyReasonCode.UNKNOWN_DATA_SENSITIVITY)
            return deny(PolicyReasonCode.UNKNOWN_DATA_SENSITIVITY)
        reasons.append(PolicyReasonCode.DATA_SENSITIVITY_MISMATCH)
        return deny(PolicyReasonCode.DATA_SENSITIVITY_MISMATCH)

    matched.extend(allows)

    if request.action is GovernanceAction.DISPLAY_FIELDS:
        if request.scope.data_sensitivity is DataSensitivity.CONTACT_PII:
            if not _field_allow_covers(request, allows):
                reasons.append(PolicyReasonCode.FIELD_SCOPE_NOT_COVERED)
                return deny(PolicyReasonCode.FIELD_SCOPE_NOT_COVERED)

    # 7) hard stale for time-sensitive actions (STAGE_FOR_REVIEW excluded)
    if request.freshness_status is FreshnessStatus.HARD_STALE and request.action in _HARD_STALE_DENY_ACTIONS:
        reasons.append(PolicyReasonCode.HARD_STALE)
        return deny(PolicyReasonCode.HARD_STALE)

    # 8) review / staging
    if request.action is GovernanceAction.STAGE_FOR_REVIEW:
        required = _required_obligations(allows)
        if not _obligations_fulfilled(required, request.fulfilled_obligations):
            reasons.append(PolicyReasonCode.OBLIGATION_UNSATISFIED)
            return quarantine(PolicyReasonCode.OBLIGATION_UNSATISFIED)
        reasons.append(PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW)
        return quarantine(PolicyReasonCode.STAGED_FOR_HUMAN_REVIEW)

    if request.action in _RUNTIME_ACTIONS:
        if request.review_status in {ReviewStatus.QUARANTINED, ReviewStatus.PENDING_HUMAN}:
            reasons.append(PolicyReasonCode.CONTENT_NOT_APPROVED)
            return deny(PolicyReasonCode.CONTENT_NOT_APPROVED)
        if request.review_status is not ReviewStatus.APPROVED:
            reasons.append(PolicyReasonCode.CONTENT_NOT_APPROVED)
            return deny(PolicyReasonCode.CONTENT_NOT_APPROVED)
        if request.publication_state is not PublicationState.PUBLISHED:
            reasons.append(PolicyReasonCode.CONTENT_NOT_PUBLISHED)
            return deny(PolicyReasonCode.CONTENT_NOT_PUBLISHED)
        if request.action is GovernanceAction.DISPLAY_FIELDS:
            if not request.scope.field_names:
                reasons.append(PolicyReasonCode.FIELD_SCOPE_NOT_COVERED)
                return deny(PolicyReasonCode.FIELD_SCOPE_NOT_COVERED)
            if not _field_allow_covers(request, allows):
                reasons.append(PolicyReasonCode.FIELD_SCOPE_NOT_COVERED)
                return deny(PolicyReasonCode.FIELD_SCOPE_NOT_COVERED)

    if request.action is GovernanceAction.PUBLISH:
        if request.review_status is not ReviewStatus.APPROVED:
            reasons.append(PolicyReasonCode.CONTENT_NOT_APPROVED)
            return deny(PolicyReasonCode.CONTENT_NOT_APPROVED)

    # 9) feature / connector / automation gates
    if not request.feature_enabled:
        reasons.append(PolicyReasonCode.FEATURE_DISABLED)
        return deny(PolicyReasonCode.FEATURE_DISABLED)

    if request.action in _CONNECTOR_ACTIONS and not request.connector_enabled:
        reasons.append(PolicyReasonCode.CONNECTOR_DISABLED)
        return deny(PolicyReasonCode.CONNECTOR_DISABLED)

    if request.automated and request.action in {GovernanceAction.FETCH, GovernanceAction.REFRESH}:
        if request.automation_status is AutomationStatus.DISABLED:
            reasons.append(PolicyReasonCode.AUTOMATION_DISABLED)
            return deny(PolicyReasonCode.AUTOMATION_DISABLED)
        if request.automation_status is AutomationStatus.MANUAL_ONLY:
            reasons.append(PolicyReasonCode.AUTOMATION_DISABLED)
            return deny(PolicyReasonCode.AUTOMATION_DISABLED)

    # 10) obligation fulfillment — before any action-specific ALLOW / VERIFY_ONLY
    required = _required_obligations(allows)
    if required and not _obligations_fulfilled(required, request.fulfilled_obligations):
        reasons.append(PolicyReasonCode.OBLIGATION_UNSATISFIED)
        return deny(PolicyReasonCode.OBLIGATION_UNSATISFIED)

    # 11) action-specific outcomes
    if request.action is GovernanceAction.POINT_LOOKUP:
        if request.mode is EvaluationMode.VERIFY_ONLY:
            reasons.append(PolicyReasonCode.VERIFY_ONLY_REQUIRED)
            return verify_only(PolicyReasonCode.VERIFY_ONLY_REQUIRED)
        reasons.append(PolicyReasonCode.ALLOW_EXPLICIT)
        return allow(PolicyReasonCode.ALLOW_EXPLICIT)

    if request.mode is EvaluationMode.VERIFY_ONLY:
        if (
            request.action in _STORAGE_ACTIONS
            or request.action is GovernanceAction.PUBLISH
            or request.action in _RUNTIME_ACTIONS
        ):
            reasons.append(PolicyReasonCode.VERIFY_ONLY_ACTION_FORBIDDEN)
            return deny(PolicyReasonCode.VERIFY_ONLY_ACTION_FORBIDDEN)

    if request.action is GovernanceAction.PUBLISH:
        if request.automated:
            reasons.append(PolicyReasonCode.AUTOMATED_PUBLISH_FORBIDDEN)
            return deny(PolicyReasonCode.AUTOMATED_PUBLISH_FORBIDDEN)
        if not _human_review_fulfilled(required, request.fulfilled_obligations):
            reasons.append(PolicyReasonCode.OBLIGATION_UNSATISFIED)
            return deny(PolicyReasonCode.OBLIGATION_UNSATISFIED)
        reasons.append(PolicyReasonCode.ALLOW_EXPLICIT)
        return allow(PolicyReasonCode.ALLOW_EXPLICIT)

    if request.action in _STORAGE_ACTIONS:
        if not _retention_fulfilled(required, request.fulfilled_obligations):
            reasons.append(PolicyReasonCode.OBLIGATION_UNSATISFIED)
            return deny(PolicyReasonCode.OBLIGATION_UNSATISFIED)
        reasons.append(PolicyReasonCode.ALLOW_EXPLICIT)
        return allow(PolicyReasonCode.ALLOW_EXPLICIT)

    reasons.append(PolicyReasonCode.ALLOW_EXPLICIT)
    return allow(PolicyReasonCode.ALLOW_EXPLICIT)


# ---------------------------------------------------------------------------
# Credential, grant matching, freshness, and helpers
# ---------------------------------------------------------------------------


def _requires_verified_credential(request: PolicyEvaluationRequest) -> bool:
    """True when credential state is material to the requested directory/PII action."""
    return (
        request.scope.data_sensitivity in _CREDENTIAL_SENSITIVITIES
        and request.action in _CREDENTIAL_BEARING_ACTIONS
    )


def _data_sensitivity_matches_request(
    grant: ScopedPermissionGrant,
    request: PolicyEvaluationRequest,
) -> bool:
    if grant.scope.data_sensitivity is DataSensitivity.UNKNOWN_RESTRICTED:
        return False
    return grant.scope.data_sensitivity is request.scope.data_sensitivity


def _has_unknown_restricted_grant(grants: Sequence[ScopedPermissionGrant]) -> bool:
    return any(g.scope.data_sensitivity is DataSensitivity.UNKNOWN_RESTRICTED for g in grants)


def _structurally_matching_grants(request: PolicyEvaluationRequest) -> list[ScopedPermissionGrant]:
    matched: list[ScopedPermissionGrant] = []
    for grant in request.grants:
        if not _grant_structurally_matches_request(grant, request):
            continue
        matched.append(grant)
    return matched


def _sensitivity_matching_grants(
    request: PolicyEvaluationRequest,
    structural_matches: Sequence[ScopedPermissionGrant],
) -> list[ScopedPermissionGrant]:
    return [g for g in structural_matches if _data_sensitivity_matches_request(g, request)]


def _grant_structurally_matches_request(
    grant: ScopedPermissionGrant,
    request: PolicyEvaluationRequest,
) -> bool:
    if grant.policy_version_id != request.policy_version_id:
        return False
    if grant.action != request.action:
        return False
    if grant.scope.source_id != request.scope.source_id:
        return False
    req_resource = request.scope.resource_id
    grant_resource = grant.scope.resource_id
    if req_resource is not None:
        if grant_resource != req_resource:
            return False
    for field in (
        "audience",
        "purpose",
        "jurisdiction",
        "environment",
        "channel",
    ):
        if getattr(grant.scope, field) != getattr(request.scope, field):
            return False
    return True


def _is_valid_freshness_status(value: object) -> bool:
    return isinstance(value, FreshnessStatus)


def _serialize_freshness_status(value: object) -> str:
    if isinstance(value, FreshnessStatus):
        return value.value
    return _INVALID_FRESHNESS_STATUS_SENTINEL


def _freshness_blocks_allow(
    request: PolicyEvaluationRequest,
    matched: Sequence[ScopedPermissionGrant],
    reasons: list[PolicyReasonCode],
) -> PolicyEvaluationResult | None:
    if request.freshness_status is FreshnessStatus.FRESH:
        return None

    def deny(code: PolicyReasonCode) -> PolicyEvaluationResult:
        return _finalize(request, PolicyOutcome.DENY, _with_primary(code, reasons), matched)

    if request.freshness_status is FreshnessStatus.SOFT_STALE:
        reasons.append(PolicyReasonCode.SOFT_STALE_REQUIRES_REVIEW)
        return deny(PolicyReasonCode.SOFT_STALE_REQUIRES_REVIEW)
    if request.freshness_status is FreshnessStatus.HARD_STALE:
        reasons.append(PolicyReasonCode.HARD_STALE)
        return deny(PolicyReasonCode.HARD_STALE)
    if request.freshness_status is FreshnessStatus.UNKNOWN_AGE:
        reasons.append(PolicyReasonCode.UNKNOWN_AGE_DENIED)
        return deny(PolicyReasonCode.UNKNOWN_AGE_DENIED)
    reasons.append(PolicyReasonCode.INVALID_REQUEST)
    return deny(PolicyReasonCode.INVALID_REQUEST)


def _freshness_blocks_verify_only(
    request: PolicyEvaluationRequest,
    matched: Sequence[ScopedPermissionGrant],
    reasons: list[PolicyReasonCode],
) -> PolicyEvaluationResult | None:
    if request.freshness_status is FreshnessStatus.FRESH:
        return None

    def deny(code: PolicyReasonCode) -> PolicyEvaluationResult:
        return _finalize(request, PolicyOutcome.DENY, _with_primary(code, reasons), matched)

    if request.freshness_status is FreshnessStatus.HARD_STALE:
        reasons.append(PolicyReasonCode.HARD_STALE)
        return deny(PolicyReasonCode.HARD_STALE)
    if request.freshness_status in {
        FreshnessStatus.SOFT_STALE,
        FreshnessStatus.UNKNOWN_AGE,
    }:
        return None
    reasons.append(PolicyReasonCode.INVALID_REQUEST)
    return deny(PolicyReasonCode.INVALID_REQUEST)


def _grant_expired(grant: ScopedPermissionGrant, at: datetime) -> bool:
    if grant.valid_until is not None and at > grant.valid_until:
        return True
    return False


def _grant_in_validity_window(grant: ScopedPermissionGrant, at: datetime) -> bool:
    if at < grant.valid_from:
        return False
    if _grant_expired(grant, at):
        return False
    return True


def _field_allow_covers(request: PolicyEvaluationRequest, allows: Sequence[ScopedPermissionGrant]) -> bool:
    requested = set(request.scope.field_names)
    if not requested:
        return False
    covered: set[str] = set()
    for grant in allows:
        covered.update(grant.scope.field_names)
    return requested.issubset(covered)


def _field_denied(request: PolicyEvaluationRequest, denies: Sequence[ScopedPermissionGrant]) -> bool:
    requested = set(request.scope.field_names)
    if not requested:
        return True
    for grant in denies:
        denied = set(grant.scope.field_names)
        if requested.intersection(denied):
            return True
    return False


def _obligation_canonical_key(ob: PermissionObligation) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (ob.kind.value, tuple(sorted(ob.parameters, key=lambda pair: pair[0])))


def _canonical_obligations(obligations: Sequence[PermissionObligation]) -> Tuple[PermissionObligation, ...]:
    by_key: dict[tuple[str, tuple[tuple[str, str], ...]], PermissionObligation] = {}
    for ob in obligations:
        by_key.setdefault(_obligation_canonical_key(ob), ob)
    return tuple(by_key[k] for k in sorted(by_key))


def _required_obligations(grants: Sequence[ScopedPermissionGrant]) -> Tuple[PermissionObligation, ...]:
    collected: list[PermissionObligation] = []
    for grant in grants:
        collected.extend(grant.obligations)
    return _canonical_obligations(collected)


def _obligations_fulfilled(
    required: Sequence[PermissionObligation],
    fulfilled: Sequence[PermissionObligation],
) -> bool:
    fulfilled_keys = {_obligation_canonical_key(o) for o in fulfilled}
    for ob in required:
        if _obligation_canonical_key(ob) not in fulfilled_keys:
            return False
    return True


def _retention_fulfilled(
    required: Sequence[PermissionObligation],
    fulfilled: Sequence[PermissionObligation],
) -> bool:
    needed = [o for o in required if o.kind is ObligationKind.RETENTION_CLASS]
    if not needed:
        return False
    return _obligations_fulfilled(needed, fulfilled)


def _human_review_fulfilled(
    required: Sequence[PermissionObligation],
    fulfilled: Sequence[PermissionObligation],
) -> bool:
    needed = [o for o in required if o.kind is ObligationKind.HUMAN_REVIEW]
    if not needed:
        return False
    return _obligations_fulfilled(needed, fulfilled)


def _sort_grants(grants: Sequence[ScopedPermissionGrant]) -> Tuple[ScopedPermissionGrant, ...]:
    return tuple(sorted(grants, key=lambda grant: grant.grant_id))


def _with_primary(primary: PolicyReasonCode, codes: list[PolicyReasonCode]) -> Tuple[PolicyReasonCode, ...]:
    secondary = sorted(
        {code for code in codes if code is not primary},
        key=lambda code: code.value,
    )
    return (primary, *secondary)


def _finalize(
    request: PolicyEvaluationRequest,
    outcome: PolicyOutcome,
    reason_codes: Tuple[PolicyReasonCode, ...],
    matched: Sequence[ScopedPermissionGrant],
) -> PolicyEvaluationResult:
    sorted_matched = _sort_grants(matched)
    primary = reason_codes[0]
    required: Tuple[PermissionObligation, ...] = tuple()
    if outcome is PolicyOutcome.ALLOW:
        required = _required_obligations(sorted_matched)
    elif outcome is PolicyOutcome.QUARANTINE and request.action is GovernanceAction.STAGE_FOR_REVIEW:
        required = _required_obligations(sorted_matched)
    fingerprint = _decision_fingerprint(request, outcome, reason_codes, sorted_matched)
    return PolicyEvaluationResult(
        outcome=outcome,
        primary_reason=primary,
        reason_codes=reason_codes,
        matched_grant_ids=tuple(g.grant_id for g in sorted_matched),
        required_obligations=required,
        policy_version_id=request.policy_version_id,
        decision_fingerprint=fingerprint,
    )


def _decision_fingerprint(
    request: PolicyEvaluationRequest,
    outcome: PolicyOutcome,
    reason_codes: Sequence[PolicyReasonCode],
    matched: Sequence[ScopedPermissionGrant],
) -> str:
    if not reason_codes:
        raise ValueError("reason_codes_empty")
    sorted_matched = _sort_grants(matched)
    canonical_fulfilled = _canonical_obligations(request.fulfilled_obligations)
    payload = {
        "algorithm_version": EVALUATOR_ALGORITHM_VERSION,
        "policy_version_id": request.policy_version_id,
        "source_id": request.scope.source_id,
        "resource_id": request.scope.resource_id,
        "action": request.action.value,
        "field_names": sorted(request.scope.field_names),
        "data_sensitivity": request.scope.data_sensitivity.value,
        "audience": request.scope.audience,
        "purpose": request.scope.purpose,
        "jurisdiction": request.scope.jurisdiction,
        "environment": request.scope.environment,
        "channel": request.scope.channel,
        "evaluation_at": request.evaluation_at.isoformat(),
        "license_status": request.license_status.value,
        "source_operational_status": request.source_operational_status.value,
        "credential_status": request.credential_status.value,
        "freshness_status": _serialize_freshness_status(request.freshness_status),
        "review_status": request.review_status.value,
        "publication_state": request.publication_state.value,
        "automation_status": request.automation_status.value,
        "feature_enabled": request.feature_enabled,
        "connector_enabled": request.connector_enabled,
        "automated": request.automated,
        "mode": request.mode.value,
        "outcome": outcome.value,
        "primary_reason": reason_codes[0].value,
        "reason_codes": sorted(c.value for c in reason_codes),
        "grants": [
            {
                "grant_id": g.grant_id,
                "decision": g.decision.value,
                "action": g.action.value,
                "resource_id": g.scope.resource_id,
                "data_sensitivity": g.scope.data_sensitivity.value,
            }
            for g in sorted_matched
        ],
        "fulfilled_obligations": [
            {
                "kind": o.kind.value,
                "parameters": sorted(o.parameters, key=lambda pair: pair[0]),
            }
            for o in canonical_fulfilled
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_unique_grants(grants: Sequence[ScopedPermissionGrant]) -> None:
    seen: set[str] = set()
    for grant in grants:
        if grant.grant_id in seen:
            raise ValueError("grants_duplicate")
        seen.add(grant.grant_id)


def _assert_unique_obligations(obligations: Sequence[PermissionObligation]) -> None:
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for ob in obligations:
        key = _obligation_canonical_key(ob)
        if key in seen:
            raise ValueError("fulfilled_obligations_duplicate")
        seen.add(key)


def _is_sha256_hex(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()
