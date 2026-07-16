"""Section 15-I5-A1 — Governance contract types and invariant tests (pure)."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.services.governance.contracts import (
    CONTRACT_VERSION,
    FAIL_CLOSED_DEFAULTS,
    GOVERNED_AUTO_PUBLICATION_ALLOWED,
    ApprovalExecutionAttribution,
    AuthorityTier,
    AutomationStatus,
    CredentialValidityStatus,
    DataSensitivity,
    EntityClass,
    FreshnessStatus,
    GovernanceAction,
    GovernanceEventKind,
    GovernanceEventStamp,
    GovernanceLineageEdge,
    IdentifierNamespace,
    IdentifierScope,
    IngestionAttemptOutcome,
    LicenseStatus,
    NormalizedArtifactIdentity,
    ObligationKind,
    PermissionDecision,
    PermissionObligation,
    PermissionScope,
    PolicyOutcome,
    PublicationState,
    RawSnapshotIdentity,
    ReviewStatus,
    ScopedPermissionGrant,
    SourceClass,
    SourceOperationalStatus,
    VerificationMethod,
    VerifiedIdentifier,
    is_valid_publication_transition,
    is_valid_review_transition,
    outage_improves_freshness,
    quarantined_runtime_retrieval_outcome,
    review_approved_implies_published,
)

UTC = timezone.utc
HASH_A = "a" * 64
HASH_B = "b" * 64


def _aware(hours: int = 0) -> datetime:
    return datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC) + timedelta(hours=hours)


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
        valid_from=_aware(),
        evidence_ids=("ev-1",),
        obligations=(PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),)),),
    )
    base.update(overrides)
    return ScopedPermissionGrant(**base)


# --- defaults / enums ---


def test_contract_version_stable():
    assert CONTRACT_VERSION == "sedi.governance.contracts.v1"


def test_fail_closed_defaults():
    d = FAIL_CLOSED_DEFAULTS
    assert d.authority_tier is AuthorityTier.UNKNOWN
    assert d.operational_status is SourceOperationalStatus.DISABLED
    assert d.automation_status is AutomationStatus.DISABLED
    assert d.license_status is LicenseStatus.UNKNOWN
    assert d.permission_decision is PermissionDecision.UNKNOWN_DENY
    assert d.review_status is ReviewStatus.QUARANTINED
    assert d.publication_state is PublicationState.UNPUBLISHED
    assert d.credential_validity is CredentialValidityStatus.UNVERIFIED
    assert d.freshness_status is FreshnessStatus.UNKNOWN_AGE
    assert d.data_sensitivity is DataSensitivity.UNKNOWN_RESTRICTED
    assert d.governed_auto_publication_allowed is False
    assert GOVERNED_AUTO_PUBLICATION_ALLOWED is False


def test_string_enum_stability_samples():
    assert SourceClass.KNOWLEDGE_DOCUMENT.value == "knowledge_document"
    assert AuthorityTier.UNKNOWN.value == "unknown"
    assert AutomationStatus.SCHEDULED_STAGE_ONLY.value == "scheduled_stage_only"
    assert GovernanceAction.PUBLISH.value == "publish"
    assert IngestionAttemptOutcome.NO_CHANGE.value == "no_change"
    assert PolicyOutcome.QUARANTINE.value == "quarantine"


def test_no_auto_publication_state_and_state_separation():
    assert IngestionAttemptOutcome.NO_CHANGE not in ReviewStatus.__members__.values()
    assert "NO_CHANGE" not in ReviewStatus.__members__
    assert "AUTO_PUBLISH" not in AutomationStatus.__members__
    assert "FULL_PIPELINE" not in AutomationStatus.__members__
    assert review_approved_implies_published() is False
    assert outage_improves_freshness() is False
    assert quarantined_runtime_retrieval_outcome() is PolicyOutcome.DENY


def test_objects_are_frozen():
    scope = _scope()
    with pytest.raises(FrozenInstanceError):
        scope.source_id = "x"  # type: ignore[misc]
    stamp = GovernanceEventStamp(_aware(), _aware(1), 1)
    with pytest.raises(FrozenInstanceError):
        stamp.event_version = 2  # type: ignore[misc]


# --- PermissionScope / Grant ---


def test_permission_scope_rejects_empty_and_duplicate_fields():
    with pytest.raises(ValueError, match="field_names"):
        _scope(field_names=("title", "title"))
    with pytest.raises(ValueError, match="field_names"):
        _scope(field_names=("",))
    with pytest.raises(ValueError, match="source_id"):
        _scope(source_id="")


def test_permission_scope_allows_empty_field_set():
    s = _scope(field_names=())
    assert s.field_names == ()


def test_grant_requires_evidence_for_explicit_decisions():
    with pytest.raises(ValueError, match="evidence_required"):
        _grant(evidence_ids=(), decision=PermissionDecision.ALLOW_EXPLICIT)
    with pytest.raises(ValueError, match="evidence_required"):
        _grant(evidence_ids=(), decision=PermissionDecision.DENY_EXPLICIT)
    with pytest.raises(ValueError, match="evidence_required"):
        _grant(evidence_ids=(), decision=PermissionDecision.POLICY_CONFLICT)


def test_grant_unknown_deny_without_evidence_ok():
    g = _grant(
        decision=PermissionDecision.UNKNOWN_DENY,
        evidence_ids=(),
        obligations=(),
    )
    assert g.decision is PermissionDecision.UNKNOWN_DENY


def test_grant_rejects_inverted_window_and_naive_time():
    with pytest.raises(ValueError, match="validity_window_inverted"):
        _grant(valid_from=_aware(2), valid_until=_aware(1))
    with pytest.raises(ValueError, match="timezone_aware"):
        _grant(valid_from=datetime(2026, 7, 16, 12, 0, 0))


def test_store_allow_requires_retention_obligation():
    with pytest.raises(ValueError, match="retention_class"):
        _grant(
            action=GovernanceAction.STORE_RAW,
            obligations=(PermissionObligation(ObligationKind.ATTRIBUTION, (("a", "b"),)),),
        )
    ok = _grant(
        action=GovernanceAction.STORE_NORMALIZED,
        obligations=(
            PermissionObligation(ObligationKind.RETENTION_CLASS, (("class", "short"),)),
        ),
    )
    assert ok.action is GovernanceAction.STORE_NORMALIZED


def test_duplicate_evidence_and_obligations_rejected():
    with pytest.raises(ValueError, match="evidence_ids_duplicate"):
        _grant(evidence_ids=("ev-1", "ev-1"))
    obl = PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),))
    with pytest.raises(ValueError, match="obligations_duplicate"):
        _grant(obligations=(obl, PermissionObligation(ObligationKind.ATTRIBUTION, (("text", "cite"),))))


# --- Snapshot identities ---


def test_raw_snapshot_hash_and_no_parser_field():
    raw = RawSnapshotIdentity(resource_id="res-1", raw_content_hash=HASH_A)
    assert raw.raw_content_hash == HASH_A
    assert not hasattr(raw, "parser_version")
    with pytest.raises(ValueError, match="sha256"):
        RawSnapshotIdentity(resource_id="res-1", raw_content_hash="abc")
    with pytest.raises(ValueError, match="sha256"):
        RawSnapshotIdentity(resource_id="res-1", raw_content_hash="A" * 64)


def test_normalized_artifact_separates_parser():
    raw = RawSnapshotIdentity(resource_id="res-1", raw_content_hash=HASH_A)
    n1 = NormalizedArtifactIdentity(raw, "html", "1.0", HASH_B)
    n2 = NormalizedArtifactIdentity(raw, "html", "2.0", "c" * 64)
    assert n1.raw_snapshot == n2.raw_snapshot
    assert n1.parser_version != n2.parser_version


# --- Bitemporal / approval ---


def test_bitemporal_stamp_allows_late_event_requires_aware():
    late = GovernanceEventStamp(
        effective_at=_aware(0),
        recorded_at=_aware(5),
        event_version=1,
    )
    assert late.recorded_at > late.effective_at
    with pytest.raises(ValueError, match="timezone_aware"):
        GovernanceEventStamp(datetime(2026, 1, 1), _aware(), 1)


def test_approver_executor_separation():
    attr = ApprovalExecutionAttribution(
        approval_event_id="ap-1",
        approved_by_actor_id="human-1",
        executed_by_service="kb-publisher",
    )
    assert attr.execution_confirmed() is False
    confirmed = ApprovalExecutionAttribution(
        approval_event_id="ap-1",
        approved_by_actor_id="human-1",
        executed_by_service="kb-publisher",
        execution_event_id="ex-1",
    )
    assert confirmed.execution_confirmed() is True
    assert confirmed.approved_by_actor_id != confirmed.executed_by_service


# --- Identifiers / lineage ---


def test_namespace_requires_issuer():
    with pytest.raises(ValueError, match="issuer_authority_id"):
        IdentifierNamespace(
            issuer_authority_id="",
            namespace="irimc.license",
            namespace_version="1",
            scope=IdentifierScope.NATIONAL_REGISTRY,
            entity_class=EntityClass.PRACTITIONER,
        )


def test_verified_identifier_rejects_active_candidate_match():
    ns = IdentifierNamespace(
        issuer_authority_id="irimc",
        namespace="irimc.license",
        namespace_version="1",
        scope=IdentifierScope.NATIONAL_REGISTRY,
        entity_class=EntityClass.PRACTITIONER,
    )
    with pytest.raises(ValueError, match="active_candidate_match"):
        VerifiedIdentifier(
            namespace=ns,
            native_value="123",
            normalized_value="123",
            status=CredentialValidityStatus.ACTIVE,
            verification_method=VerificationMethod.CANDIDATE_MATCH_ONLY,
        )
    ok = VerifiedIdentifier(
        namespace=ns,
        native_value="123",
        normalized_value="123",
        status=CredentialValidityStatus.ACTIVE,
        verification_method=VerificationMethod.OFFICIAL_POINT_LOOKUP,
        effective_from=_aware(),
    )
    assert ok.status is CredentialValidityStatus.ACTIVE


def test_lineage_self_edge_forbidden():
    stamp = GovernanceEventStamp(_aware(), _aware(1), 1)
    with pytest.raises(ValueError, match="self_edge"):
        GovernanceLineageEdge(
            event_id="e1",
            kind=GovernanceEventKind.SUPERSEDES,
            from_ref="pub:1",
            to_ref="pub:1",
            stamp=stamp,
        )
    edge = GovernanceLineageEdge(
        event_id="e1",
        kind=GovernanceEventKind.REVOKES,
        from_ref="rev:1",
        to_ref="pub:1",
        stamp=stamp,
    )
    assert edge.kind is GovernanceEventKind.REVOKES


# --- Transitions ---


def test_review_transitions():
    assert is_valid_review_transition(
        ReviewStatus.QUARANTINED, ReviewStatus.PENDING_HUMAN
    )
    assert not is_valid_review_transition(
        ReviewStatus.QUARANTINED, ReviewStatus.APPROVED
    )
    assert is_valid_review_transition(
        ReviewStatus.PENDING_HUMAN, ReviewStatus.APPROVED
    )
    assert is_valid_review_transition(
        ReviewStatus.PENDING_HUMAN, ReviewStatus.REJECTED
    )
    assert not is_valid_review_transition(
        ReviewStatus.APPROVED, ReviewStatus.PENDING_HUMAN
    )


def test_publication_transitions():
    assert is_valid_publication_transition(
        PublicationState.UNPUBLISHED, PublicationState.PUBLISHED
    )
    assert is_valid_publication_transition(
        PublicationState.PUBLISHED, PublicationState.SUPERSEDED
    )
    assert is_valid_publication_transition(
        PublicationState.PUBLISHED, PublicationState.WITHDRAWN
    )
    assert is_valid_publication_transition(
        PublicationState.PUBLISHED, PublicationState.SUSPENDED
    )
    assert not is_valid_publication_transition(
        PublicationState.WITHDRAWN, PublicationState.PUBLISHED
    )
    assert not is_valid_publication_transition(
        PublicationState.SUPERSEDED, PublicationState.PUBLISHED
    )


# --- Import / source hygiene ---


def test_contracts_module_stdlib_only_no_models_or_userdoctor():
    mod_path = Path(
        inspect.getfile(
            __import__("backend.app.services.governance.contracts", fromlist=["*"])
        )
    )
    source = mod_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed_import_roots = {
        "re",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "__future__",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = mod.split(".")[0] if mod else ""
            assert root in allowed_import_roots, mod
            assert not mod.startswith("backend.")
    # No identifier named UserDoctor anywhere in the module AST.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "UserDoctor"
        if isinstance(node, ast.Attribute):
            assert node.attr != "UserDoctor"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "UserDoctor" not in node.value
