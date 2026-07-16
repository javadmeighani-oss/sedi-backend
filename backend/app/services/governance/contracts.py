"""Section 15-I5-A1 — pure governance contract types and invariants.

Internal design contracts only. No ORM, API schema, I/O, env, or runtime wiring.
Stdlib-only; no application persistence or router dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple
import re

CONTRACT_VERSION = "sedi.governance.contracts.v1"

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Enums (stable string values)
# ---------------------------------------------------------------------------


class SourceClass(str, Enum):
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    DIRECTORY = "directory"
    POINT_VERIFICATION = "point_verification"
    LEGAL_TERMS = "legal_terms"
    REVOCATION_FEED = "revocation_feed"
    DATED_ALERT = "dated_alert"


class AuthorityTier(str, Enum):
    OFFICIAL_NATIONAL = "official_national"
    OFFICIAL_INTERNATIONAL = "official_international"
    ACCREDITOR = "accreditor"
    UNIVERSITY = "university"
    EDITORIAL = "editorial"
    UNKNOWN = "unknown"


class SourceOperationalStatus(str, Enum):
    DISABLED = "disabled"
    ENABLED_IDLE = "enabled_idle"
    OUTAGE = "outage"
    SUSPENDED = "suspended"


class AutomationStatus(str, Enum):
    DISABLED = "disabled"
    MANUAL_ONLY = "manual_only"
    SCHEDULED_STAGE_ONLY = "scheduled_stage_only"


class LicenseStatus(str, Enum):
    EXPLICIT_GRANT = "explicit_grant"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    CONFLICT = "conflict"


class PermissionDecision(str, Enum):
    ALLOW_EXPLICIT = "allow_explicit"
    DENY_EXPLICIT = "deny_explicit"
    UNKNOWN_DENY = "unknown_deny"
    POLICY_CONFLICT = "policy_conflict"
    NOT_APPLICABLE = "not_applicable"


class PolicyOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    VERIFY_ONLY = "verify_only"
    QUARANTINE = "quarantine"


class GovernanceAction(str, Enum):
    DISCOVER_LINK = "discover_link"
    POINT_LOOKUP = "point_lookup"
    FETCH = "fetch"
    STORE_RAW = "store_raw"
    STORE_NORMALIZED = "store_normalized"
    TRANSFORM = "transform"
    DERIVE = "derive"
    INDEX_EMBED = "index_embed"
    CITE_LINK = "cite_link"
    DISPLAY_FIELDS = "display_fields"
    REDISTRIBUTE_EXPORT = "redistribute_export"
    REFRESH = "refresh"
    DELETE_PURGE = "delete_purge"
    STAGE_FOR_REVIEW = "stage_for_review"
    PUBLISH = "publish"


class IngestionAttemptOutcome(str, Enum):
    SUCCESS_NEW_CONTENT = "success_new_content"
    NO_CHANGE = "no_change"
    FETCH_FAILED = "fetch_failed"
    PARSE_FAILED = "parse_failed"
    PARTIAL_PARSE = "partial_parse"
    BLOCKED_POLICY = "blocked_policy"


class ReviewStatus(str, Enum):
    QUARANTINED = "quarantined"
    PENDING_HUMAN = "pending_human"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublicationState(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"
    SUSPENDED = "suspended"


class CredentialValidityStatus(str, Enum):
    UNVERIFIED = "unverified"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    SOFT_STALE = "soft_stale"
    HARD_STALE = "hard_stale"
    UNKNOWN_AGE = "unknown_age"


class DataSensitivity(str, Enum):
    PUBLIC_EDUCATIONAL = "public_educational"
    PROFESSIONAL_DIRECTORY = "professional_directory"
    CONTACT_PII = "contact_pii"
    HEALTH_ADVICE = "health_advice"
    UNKNOWN_RESTRICTED = "unknown_restricted"


class IdentifierScope(str, Enum):
    INTERNAL = "internal"
    SOURCE_NATIVE = "source_native"
    USER_PRIVATE = "user_private"
    NATIONAL_REGISTRY = "national_registry"
    AUDIT_ONLY = "audit_only"


class EntityClass(str, Enum):
    PRACTITIONER = "practitioner"
    FACILITY = "facility"
    LABORATORY = "laboratory"
    PRODUCT = "product"
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    UNKNOWN = "unknown"


class VerificationMethod(str, Enum):
    SOURCE_NATIVE_EXACT = "source_native_exact"
    OFFICIAL_POINT_LOOKUP = "official_point_lookup"
    HUMAN_REVIEWED_DOCUMENT = "human_reviewed_document"
    CANDIDATE_MATCH_ONLY = "candidate_match_only"


class ObligationKind(str, Enum):
    ATTRIBUTION = "attribution"
    FIELD_REDACTION = "field_redaction"
    RETENTION_CLASS = "retention_class"
    HUMAN_REVIEW = "human_review"
    EXPIRY = "expiry"
    LINK_ONLY = "link_only"


class GovernanceEventKind(str, Enum):
    SUPERSEDES = "supersedes"
    INVALIDATES = "invalidates"
    REVOKES = "revokes"
    DERIVED_FROM = "derived_from"
    CORRECTS = "corrects"


# ---------------------------------------------------------------------------
# Fail-closed defaults
# ---------------------------------------------------------------------------

GOVERNED_AUTO_PUBLICATION_ALLOWED: bool = False


@dataclass(frozen=True)
class FailClosedDefaults:
    """Testable fail-closed defaults for governed I5 contracts."""

    authority_tier: AuthorityTier = AuthorityTier.UNKNOWN
    operational_status: SourceOperationalStatus = SourceOperationalStatus.DISABLED
    automation_status: AutomationStatus = AutomationStatus.DISABLED
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    permission_decision: PermissionDecision = PermissionDecision.UNKNOWN_DENY
    review_status: ReviewStatus = ReviewStatus.QUARANTINED
    publication_state: PublicationState = PublicationState.UNPUBLISHED
    credential_validity: CredentialValidityStatus = CredentialValidityStatus.UNVERIFIED
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN_AGE
    data_sensitivity: DataSensitivity = DataSensitivity.UNKNOWN_RESTRICTED
    governed_auto_publication_allowed: bool = False


FAIL_CLOSED_DEFAULTS = FailClosedDefaults()


def quarantined_runtime_retrieval_outcome() -> PolicyOutcome:
    """Quarantined content must not be retrieved at runtime (equals DENY)."""
    return PolicyOutcome.DENY


# ---------------------------------------------------------------------------
# Validation helpers (pure)
# ---------------------------------------------------------------------------


def _require_nonempty_str(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}_required")
    if value != value.strip():
        raise ValueError(f"{field_name}_untrimmed")
    return value


def _require_aware(dt: datetime, field_name: str) -> datetime:
    if not isinstance(dt, datetime):
        raise ValueError(f"{field_name}_must_be_datetime")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")
    return dt


def _freeze_str_tuple(
    values: Sequence[str],
    *,
    field_name: str,
    allow_empty: bool = False,
) -> Tuple[str, ...]:
    if values is None:
        raise ValueError(f"{field_name}_required")
    items = tuple(values)
    if not allow_empty and len(items) == 0:
        raise ValueError(f"{field_name}_empty")
    seen = set()
    normalized: list[str] = []
    for item in items:
        s = _require_nonempty_str(item, field_name)
        if s in seen:
            raise ValueError(f"{field_name}_duplicate")
        seen.add(s)
        normalized.append(s)
    return tuple(normalized)


def is_valid_sha256_hex(value: str) -> bool:
    return isinstance(value, str) and bool(_SHA256_HEX_RE.fullmatch(value))


def require_sha256_hex(value: str, field_name: str = "content_hash") -> str:
    if not is_valid_sha256_hex(value):
        raise ValueError(f"{field_name}_invalid_sha256_hex")
    return value


# ---------------------------------------------------------------------------
# Transition invariants
# ---------------------------------------------------------------------------

REVIEW_TRANSITIONS: Mapping[ReviewStatus, frozenset[ReviewStatus]] = {
    ReviewStatus.QUARANTINED: frozenset({ReviewStatus.PENDING_HUMAN}),
    ReviewStatus.PENDING_HUMAN: frozenset(
        {ReviewStatus.APPROVED, ReviewStatus.REJECTED}
    ),
    ReviewStatus.APPROVED: frozenset(),
    ReviewStatus.REJECTED: frozenset(),
}

PUBLICATION_TRANSITIONS: Mapping[PublicationState, frozenset[PublicationState]] = {
    PublicationState.UNPUBLISHED: frozenset({PublicationState.PUBLISHED}),
    PublicationState.PUBLISHED: frozenset(
        {
            PublicationState.SUPERSEDED,
            PublicationState.WITHDRAWN,
            PublicationState.SUSPENDED,
        }
    ),
    PublicationState.SUPERSEDED: frozenset(),
    PublicationState.WITHDRAWN: frozenset(),
    PublicationState.SUSPENDED: frozenset(),
}


def is_valid_review_transition(current: ReviewStatus, nxt: ReviewStatus) -> bool:
    return nxt in REVIEW_TRANSITIONS.get(current, frozenset())


def is_valid_publication_transition(
    current: PublicationState, nxt: PublicationState
) -> bool:
    return nxt in PUBLICATION_TRANSITIONS.get(current, frozenset())


def review_approved_implies_published() -> bool:
    """APPROVED alone does not mean PUBLISHED."""
    return False


def outage_improves_freshness() -> bool:
    """OUTAGE must not improve freshness interpretation."""
    return False


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PermissionScope:
    source_id: str
    data_sensitivity: DataSensitivity
    field_names: Tuple[str, ...]
    audience: str
    purpose: str
    jurisdiction: str
    environment: str
    channel: str
    resource_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_nonempty_str(self.source_id, "source_id")
        if self.resource_id is not None:
            _require_nonempty_str(self.resource_id, "resource_id")
        object.__setattr__(
            self,
            "field_names",
            _freeze_str_tuple(
                self.field_names,
                field_name="field_names",
                allow_empty=True,
            ),
        )
        for name in (
            "audience",
            "purpose",
            "jurisdiction",
            "environment",
            "channel",
        ):
            _require_nonempty_str(getattr(self, name), name)
        if not isinstance(self.data_sensitivity, DataSensitivity):
            raise ValueError("data_sensitivity_invalid")


@dataclass(frozen=True)
class PermissionObligation:
    kind: ObligationKind
    parameters: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObligationKind):
            raise ValueError("obligation_kind_invalid")
        seen_keys: set[str] = set()
        frozen: list[Tuple[str, str]] = []
        for pair in self.parameters:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("obligation_parameter_invalid")
            key = _require_nonempty_str(pair[0], "obligation_parameter_key")
            val = _require_nonempty_str(pair[1], "obligation_parameter_value")
            if key in seen_keys:
                raise ValueError("obligation_parameter_duplicate")
            seen_keys.add(key)
            frozen.append((key, val))
        object.__setattr__(self, "parameters", tuple(frozen))


@dataclass(frozen=True)
class ScopedPermissionGrant:
    grant_id: str
    policy_version_id: str
    action: GovernanceAction
    decision: PermissionDecision
    scope: PermissionScope
    valid_from: datetime
    evidence_ids: Tuple[str, ...]
    obligations: Tuple[PermissionObligation, ...]
    valid_until: Optional[datetime] = None

    def __post_init__(self) -> None:
        _require_nonempty_str(self.grant_id, "grant_id")
        _require_nonempty_str(self.policy_version_id, "policy_version_id")
        if not isinstance(self.action, GovernanceAction):
            raise ValueError("action_invalid")
        if not isinstance(self.decision, PermissionDecision):
            raise ValueError("decision_invalid")
        if not isinstance(self.scope, PermissionScope):
            raise ValueError("scope_invalid")
        _require_aware(self.valid_from, "valid_from")
        if self.valid_until is not None:
            _require_aware(self.valid_until, "valid_until")
            if self.valid_until < self.valid_from:
                raise ValueError("validity_window_inverted")

        object.__setattr__(
            self,
            "evidence_ids",
            _freeze_str_tuple(
                self.evidence_ids,
                field_name="evidence_ids",
                allow_empty=True,
            ),
        )
        obs = tuple(self.obligations)
        seen_obs: set[Tuple[object, ...]] = set()
        for ob in obs:
            if not isinstance(ob, PermissionObligation):
                raise ValueError("obligation_invalid")
            key = (ob.kind, ob.parameters)
            if key in seen_obs:
                raise ValueError("obligations_duplicate")
            seen_obs.add(key)
        object.__setattr__(self, "obligations", obs)

        needs_evidence = self.decision in (
            PermissionDecision.ALLOW_EXPLICIT,
            PermissionDecision.DENY_EXPLICIT,
            PermissionDecision.POLICY_CONFLICT,
        )
        if needs_evidence and len(self.evidence_ids) == 0:
            raise ValueError("evidence_required_for_explicit_decision")

        if self.decision is PermissionDecision.ALLOW_EXPLICIT and self.action in (
            GovernanceAction.STORE_RAW,
            GovernanceAction.STORE_NORMALIZED,
        ):
            if not any(o.kind is ObligationKind.RETENTION_CLASS for o in self.obligations):
                raise ValueError("retention_class_required_for_store_allow")


@dataclass(frozen=True)
class RawSnapshotIdentity:
    """Raw snapshot identity: (resource_id, raw_content_hash) only — no parser."""

    resource_id: str
    raw_content_hash: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.resource_id, "resource_id")
        require_sha256_hex(self.raw_content_hash, "raw_content_hash")


@dataclass(frozen=True)
class NormalizedArtifactIdentity:
    raw_snapshot: RawSnapshotIdentity
    parser_name: str
    parser_version: str
    normalized_content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.raw_snapshot, RawSnapshotIdentity):
            raise ValueError("raw_snapshot_invalid")
        _require_nonempty_str(self.parser_name, "parser_name")
        _require_nonempty_str(self.parser_version, "parser_version")
        require_sha256_hex(self.normalized_content_hash, "normalized_content_hash")


@dataclass(frozen=True)
class GovernanceEventStamp:
    """Bitemporal stamp: effective_at vs recorded_at; late events allowed."""

    effective_at: datetime
    recorded_at: datetime
    event_version: int

    def __post_init__(self) -> None:
        _require_aware(self.effective_at, "effective_at")
        _require_aware(self.recorded_at, "recorded_at")
        if not isinstance(self.event_version, int) or self.event_version < 1:
            raise ValueError("event_version_invalid")


@dataclass(frozen=True)
class ApprovalExecutionAttribution:
    """Human approver and system executor are independent."""

    approval_event_id: str
    approved_by_actor_id: str
    executed_by_service: str
    execution_event_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_nonempty_str(self.approval_event_id, "approval_event_id")
        _require_nonempty_str(self.approved_by_actor_id, "approved_by_actor_id")
        _require_nonempty_str(self.executed_by_service, "executed_by_service")
        if self.execution_event_id is not None:
            _require_nonempty_str(self.execution_event_id, "execution_event_id")

    def execution_confirmed(self) -> bool:
        return self.execution_event_id is not None


@dataclass(frozen=True)
class IdentifierNamespace:
    issuer_authority_id: str
    namespace: str
    namespace_version: str
    scope: IdentifierScope
    entity_class: EntityClass

    def __post_init__(self) -> None:
        _require_nonempty_str(self.issuer_authority_id, "issuer_authority_id")
        _require_nonempty_str(self.namespace, "namespace")
        _require_nonempty_str(self.namespace_version, "namespace_version")
        if not isinstance(self.scope, IdentifierScope):
            raise ValueError("scope_invalid")
        if not isinstance(self.entity_class, EntityClass):
            raise ValueError("entity_class_invalid")


@dataclass(frozen=True)
class VerifiedIdentifier:
    namespace: IdentifierNamespace
    native_value: str
    normalized_value: str
    status: CredentialValidityStatus
    verification_method: VerificationMethod
    effective_from: Optional[datetime] = None
    effective_until: Optional[datetime] = None
    snapshot_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, IdentifierNamespace):
            raise ValueError("namespace_invalid")
        _require_nonempty_str(self.native_value, "native_value")
        _require_nonempty_str(self.normalized_value, "normalized_value")
        if not isinstance(self.status, CredentialValidityStatus):
            raise ValueError("status_invalid")
        if not isinstance(self.verification_method, VerificationMethod):
            raise ValueError("verification_method_invalid")
        if (
            self.status is CredentialValidityStatus.ACTIVE
            and self.verification_method is VerificationMethod.CANDIDATE_MATCH_ONLY
        ):
            raise ValueError("active_candidate_match_forbidden")
        if self.effective_from is not None:
            _require_aware(self.effective_from, "effective_from")
        if self.effective_until is not None:
            _require_aware(self.effective_until, "effective_until")
            if self.effective_from is not None and self.effective_until < self.effective_from:
                raise ValueError("effective_window_inverted")
        if self.snapshot_id is not None:
            _require_nonempty_str(self.snapshot_id, "snapshot_id")


@dataclass(frozen=True)
class GovernanceLineageEdge:
    event_id: str
    kind: GovernanceEventKind
    from_ref: str
    to_ref: str
    stamp: GovernanceEventStamp

    def __post_init__(self) -> None:
        _require_nonempty_str(self.event_id, "event_id")
        if not isinstance(self.kind, GovernanceEventKind):
            raise ValueError("kind_invalid")
        _require_nonempty_str(self.from_ref, "from_ref")
        _require_nonempty_str(self.to_ref, "to_ref")
        if self.from_ref == self.to_ref:
            raise ValueError("self_edge_forbidden")
        if not isinstance(self.stamp, GovernanceEventStamp):
            raise ValueError("stamp_invalid")
