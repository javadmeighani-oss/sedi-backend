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


# ---------------------------------------------------------------------------
# Section 15-I5-A1-R1 — expanded governance contracts (additive; stdlib-only)
# Focused safety corrections: F01–F12
# ---------------------------------------------------------------------------

EXPANDED_CONTRACT_VERSION = "sedi.governance.expanded-contracts.v1"

_ISO3166_ALPHA2_RE = re.compile(r"^[A-Z]{2}$")
_BCP47_LANGUAGE_RE = re.compile(r"^[a-z]{2}(-[A-Za-z0-9]{2,8})*$")


class GovernedAuthorityKind(str, Enum):
    CLINICAL_EVIDENCE = "clinical_evidence"
    PROVIDER_IDENTITY = "provider_identity"
    FACILITY_IDENTITY = "facility_identity"


class AuthorityUseCase(str, Enum):
    CLINICAL_ANSWER = "clinical_answer"
    PROVIDER_VERIFICATION = "provider_verification"
    FACILITY_VERIFICATION = "facility_verification"
    PROVIDER_RANKING = "provider_ranking"


class AuthoritySeparationOutcome(str, Enum):
    PERMITTED = "permitted"
    DENIED = "denied"


class KnowledgeDomain(str, Enum):
    CLINICAL_DISEASE = "clinical_disease"
    PREVENTIVE_CARE = "preventive_care"
    LIFESTYLE = "lifestyle"
    REHABILITATION = "rehabilitation"
    MENTAL_BEHAVIORAL_HEALTH = "mental_behavioral_health"
    MEDICATION_SAFETY = "medication_safety"
    LONGEVITY_EVIDENCE = "longevity_evidence"


class DiseaseSystem(str, Enum):
    NERVOUS_SYSTEM = "nervous_system"
    CARDIOVASCULAR = "cardiovascular"
    HEPATIC_BILIARY = "hepatic_biliary"
    ENDOCRINE_METABOLIC = "endocrine_metabolic"
    RENAL_URINARY = "renal_urinary"
    RESPIRATORY = "respiratory"
    GASTROINTESTINAL = "gastrointestinal"
    INFECTIOUS = "infectious"
    ONCOLOGY = "oncology"
    IMMUNE_RHEUMATOLOGY = "immune_rheumatology"
    HEMATOLOGY = "hematology"
    REPRODUCTIVE_MATERNAL = "reproductive_maternal"
    PEDIATRIC = "pediatric"
    GERIATRIC = "geriatric"
    MENTAL_BEHAVIORAL = "mental_behavioral"
    MUSCULOSKELETAL = "musculoskeletal"
    DERMATOLOGIC = "dermatologic"
    OPHTHALMOLOGIC = "ophthalmologic"
    ENT = "ent"
    ORAL_DENTAL = "oral_dental"
    MULTISYSTEM = "multisystem"
    OTHER = "other"
    UNKNOWN = "unknown"


class ClinicalDomain(str, Enum):
    ACUTE = "acute"
    CHRONIC = "chronic"
    PREVENTIVE = "preventive"
    REHABILITATIVE = "rehabilitative"
    MENTAL_BEHAVIORAL = "mental_behavioral"
    UNKNOWN = "unknown"


class ClinicalJurisdictionScope(str, Enum):
    GLOBAL = "global"
    COUNTRY = "country"
    SUBDIVISION = "subdivision"
    ORGANIZATION = "organization"


class TaxonomyMappingRelation(str, Enum):
    EXACT = "exact"
    NARROWER = "narrower"
    BROADER = "broader"
    RELATED = "related"
    UNVERIFIED = "unverified"


class EvidenceFacet(str, Enum):
    DEFINITION = "definition"
    PATIENT_EDUCATION = "patient_education"
    EPIDEMIOLOGY = "epidemiology"
    CAUSES_AND_RISK_FACTORS = "causes_and_risk_factors"
    PREVENTION = "prevention"
    SCREENING = "screening"
    COMMON_SYMPTOMS = "common_symptoms"
    RED_FLAGS = "red_flags"
    EVALUATION_EDUCATION = "evaluation_education"
    TREATMENT_EDUCATION = "treatment_education"
    MEDICATION_SAFETY = "medication_safety"
    REHABILITATION = "rehabilitation"
    NUTRITION = "nutrition"
    PHYSICAL_ACTIVITY = "physical_activity"
    SLEEP = "sleep"
    STRESS_AND_BEHAVIORAL_SUPPORT = "stress_and_behavioral_support"
    CAREGIVER_AND_FAMILY_SUPPORT = "caregiver_and_family_support"
    FOLLOW_UP_AND_MONITORING = "follow_up_and_monitoring"
    COMPLICATIONS = "complications"
    NATURAL_HISTORY = "natural_history"
    PROGNOSIS_EVIDENCE = "prognosis_evidence"
    CARE_PATHWAY = "care_pathway"
    SPECIALTY_REFERRAL = "specialty_referral"


class PreventionScope(str, Enum):
    PRIMARY_PREVENTION = "primary_prevention"
    SECONDARY_PREVENTION = "secondary_prevention"
    TERTIARY_PREVENTION = "tertiary_prevention"
    SCREENING = "screening"
    VACCINATION = "vaccination"
    RISK_REDUCTION = "risk_reduction"
    CARE_GAP_DETECTION = "care_gap_detection"


class CareScope(str, Enum):
    SELF_CARE_EDUCATION = "self_care_education"
    PREVENTIVE_CARE = "preventive_care"
    CHRONIC_CARE = "chronic_care"
    ACUTE_RED_FLAG_GUIDANCE = "acute_red_flag_guidance"
    REHABILITATION = "rehabilitation"
    CAREGIVER_SUPPORT = "caregiver_support"
    FOLLOW_UP = "follow_up"
    MONITORING = "monitoring"
    SPECIALIST_REFERRAL = "specialist_referral"
    PALLIATIVE_SUPPORT = "palliative_support"


class LongevityEvidenceScope(str, Enum):
    TOBACCO_AVOIDANCE = "tobacco_avoidance"
    NUTRITION = "nutrition"
    PHYSICAL_ACTIVITY = "physical_activity"
    SLEEP = "sleep"
    MENTAL_WELLBEING = "mental_wellbeing"
    HEALTHY_BODY_WEIGHT = "healthy_body_weight"
    BLOOD_PRESSURE = "blood_pressure"
    BLOOD_GLUCOSE = "blood_glucose"
    BLOOD_LIPIDS = "blood_lipids"
    VACCINATION = "vaccination"
    RISK_BASED_SCREENING = "risk_based_screening"
    MEDICATION_ADHERENCE_EDUCATION = "medication_adherence_education"
    SOCIAL_CONNECTION = "social_connection"
    FALL_PREVENTION = "fall_prevention"
    HEALTHY_AGEING = "healthy_ageing"
    CARE_GAP_DETECTION = "care_gap_detection"


class KnowledgePolicyDecision(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED_FOUND = "required_found"
    REQUIRED_INSUFFICIENT = "required_insufficient"
    REQUIRED_STALE = "required_stale"
    BLOCKED = "blocked"


class EvidenceUseDecision(str, Enum):
    ALLOW_WITH_CITATION = "allow_with_citation"
    ALLOW_WITH_RESTRICTIONS = "allow_with_restrictions"
    REQUIRE_HUMAN_REVIEW = "require_human_review"
    DENY_MISSING = "deny_missing"
    DENY_STALE = "deny_stale"
    DENY_CONFLICT = "deny_conflict"
    DENY_LICENSE = "deny_license"
    DENY_JURISDICTION = "deny_jurisdiction"
    DENY_REVOKED = "deny_revoked"
    DENY_QUARANTINED = "deny_quarantined"
    DENY_UNSUPPORTED_AUTHORITY = "deny_unsupported_authority"


class ContradictionStatus(str, Enum):
    NONE = "none"
    DETECTED_UNRESOLVED = "detected_unresolved"
    RESOLVED_PREFERRED_AUTHORITY = "resolved_preferred_authority"
    RESOLVED_JURISDICTION = "resolved_jurisdiction"
    ACCEPTED_DIVERGENCE = "accepted_divergence"
    BLOCKED = "blocked"


class RevocationDecision(str, Enum):
    NOT_REVOKED = "not_revoked"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    REVIEW_REQUIRED = "review_required"


class RollbackDecision(str, Enum):
    NOT_REQUIRED = "not_required"
    ELIGIBLE = "eligible"
    REQUIRED = "required"
    BLOCKED_NO_APPROVED_BASELINE = "blocked_no_approved_baseline"
    COMPLETED = "completed"


class EvidenceCriticality(str, Enum):
    GENERAL = "general"
    CLINICAL = "clinical"
    SAFETY_CRITICAL = "safety_critical"


class FreshnessUseDecision(str, Enum):
    ELIGIBLE = "eligible"
    RESTRICTED = "restricted"
    DENIED = "denied"


class PredictionUseCase(str, Enum):
    RISK_FACTOR_IDENTIFICATION = "risk_factor_identification"
    RISK_TREND = "risk_trend"
    SCREENING_DUE = "screening_due"
    MONITORING_DUE = "monitoring_due"
    CARE_GAP = "care_gap"
    RED_FLAG_DETECTION = "red_flag_detection"
    LIFESTYLE_OPPORTUNITY = "lifestyle_opportunity"
    COMPLICATION_MONITORING_NEED = "complication_monitoring_need"
    SPECIALIST_OR_FACILITY_REFERRAL_NEED = "specialist_or_facility_referral_need"
    DIAGNOSIS = "diagnosis"
    DETERMINISTIC_PROGNOSIS = "deterministic_prognosis"
    GUARANTEED_DISEASE_OUTCOME = "guaranteed_disease_outcome"
    PRECISE_REMAINING_LIFETIME = "precise_remaining_lifetime"
    MEDICATION_DOSE_CHANGE = "medication_dose_change"
    PRESCRIPTION_SUBSTITUTION = "prescription_substitution"
    TREATMENT_REPLACEMENT = "treatment_replacement"


class PredictionUseDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_MORE_DATA = "require_more_data"
    REQUIRE_CONSENT = "require_consent"
    REQUIRE_HUMAN_REVIEW = "require_human_review"
    BLOCKED = "blocked"


class PredictionReasonCode(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    CONSENT_REQUIRED = "consent_required"
    GOVERNED_EVIDENCE_REQUIRED = "governed_evidence_required"
    UNCERTAINTY_REQUIRED = "uncertainty_required"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    STALE_EVIDENCE = "stale_evidence"
    I4_SAFETY_CLEARANCE_REQUIRED = "i4_safety_clearance_required"
    AUTHORIZED_USE = "authorized_use"


PROHIBITED_PREDICTION_USE_CASES: frozenset[PredictionUseCase] = frozenset(
    {
        PredictionUseCase.DIAGNOSIS,
        PredictionUseCase.DETERMINISTIC_PROGNOSIS,
        PredictionUseCase.GUARANTEED_DISEASE_OUTCOME,
        PredictionUseCase.PRECISE_REMAINING_LIFETIME,
        PredictionUseCase.MEDICATION_DOSE_CHANGE,
        PredictionUseCase.PRESCRIPTION_SUBSTITUTION,
        PredictionUseCase.TREATMENT_REPLACEMENT,
    }
)

ALLOWING_EVIDENCE_USE_DECISIONS: frozenset[EvidenceUseDecision] = frozenset(
    {
        EvidenceUseDecision.ALLOW_WITH_CITATION,
        EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
    }
)

_BLOCKED_LICENSE_STATUSES: frozenset[LicenseStatus] = frozenset(
    {
        LicenseStatus.UNKNOWN,
        LicenseStatus.EXPIRED,
        LicenseStatus.CONFLICT,
    }
)


def _normalize_iso3166_alpha2(value: str, field_name: str) -> str:
    normalized = _require_nonempty_str(value, field_name).upper()
    if not _ISO3166_ALPHA2_RE.fullmatch(normalized):
        raise ValueError(f"{field_name}_invalid_iso3166_alpha2")
    return normalized


def _normalize_bcp47_language_tag(value: str, field_name: str) -> str:
    normalized = _require_nonempty_str(value, field_name).lower()
    if not _BCP47_LANGUAGE_RE.fullmatch(normalized):
        raise ValueError(f"{field_name}_invalid_bcp47")
    return normalized


def _normalize_normalized_term_text(value: str, field_name: str) -> str:
    text = _require_nonempty_str(value, field_name)
    return " ".join(text.split())


def _freeze_evidence_facet_tuple(
    values: Sequence[EvidenceFacet],
    *,
    field_name: str,
    allow_empty: bool = False,
) -> Tuple[EvidenceFacet, ...]:
    if values is None:
        raise ValueError(f"{field_name}_required")
    items = tuple(values)
    if not allow_empty and len(items) == 0:
        raise ValueError(f"{field_name}_empty")
    seen: set[EvidenceFacet] = set()
    normalized: list[EvidenceFacet] = []
    for item in items:
        if not isinstance(item, EvidenceFacet):
            raise ValueError(f"{field_name}_invalid")
        if item in seen:
            raise ValueError(f"{field_name}_duplicate")
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def _freeze_prediction_reason_tuple(
    values: Sequence[PredictionReasonCode],
    *,
    field_name: str,
    allow_empty: bool = False,
) -> Tuple[PredictionReasonCode, ...]:
    if values is None:
        raise ValueError(f"{field_name}_required")
    items = tuple(values)
    if not allow_empty and len(items) == 0:
        raise ValueError(f"{field_name}_empty")
    seen: set[PredictionReasonCode] = set()
    normalized: list[PredictionReasonCode] = []
    for item in items:
        if not isinstance(item, PredictionReasonCode):
            raise ValueError(f"{field_name}_invalid")
        if item in seen:
            raise ValueError(f"{field_name}_duplicate")
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def evaluate_authority_separation(
    authority_kind: GovernedAuthorityKind,
    use_case: AuthorityUseCase,
) -> AuthoritySeparationOutcome:
    if not isinstance(authority_kind, GovernedAuthorityKind):
        return AuthoritySeparationOutcome.DENIED
    if not isinstance(use_case, AuthorityUseCase):
        return AuthoritySeparationOutcome.DENIED
    if use_case is AuthorityUseCase.PROVIDER_RANKING:
        return AuthoritySeparationOutcome.DENIED
    permitted_pairs = {
        (GovernedAuthorityKind.CLINICAL_EVIDENCE, AuthorityUseCase.CLINICAL_ANSWER),
        (GovernedAuthorityKind.PROVIDER_IDENTITY, AuthorityUseCase.PROVIDER_VERIFICATION),
        (GovernedAuthorityKind.FACILITY_IDENTITY, AuthorityUseCase.FACILITY_VERIFICATION),
    }
    if (authority_kind, use_case) in permitted_pairs:
        return AuthoritySeparationOutcome.PERMITTED
    return AuthoritySeparationOutcome.DENIED


def evaluate_freshness_criticality_use(
    criticality: EvidenceCriticality,
    freshness: FreshnessStatus,
) -> FreshnessUseDecision:
    if criticality is EvidenceCriticality.SAFETY_CRITICAL:
        if freshness is FreshnessStatus.FRESH:
            return FreshnessUseDecision.ELIGIBLE
        if freshness is FreshnessStatus.SOFT_STALE:
            return FreshnessUseDecision.RESTRICTED
        return FreshnessUseDecision.DENIED
    if criticality is EvidenceCriticality.CLINICAL:
        if freshness is FreshnessStatus.FRESH:
            return FreshnessUseDecision.ELIGIBLE
        if freshness is FreshnessStatus.SOFT_STALE:
            return FreshnessUseDecision.RESTRICTED
        return FreshnessUseDecision.DENIED
    if criticality is EvidenceCriticality.GENERAL:
        if freshness is FreshnessStatus.FRESH:
            return FreshnessUseDecision.ELIGIBLE
        if freshness is FreshnessStatus.SOFT_STALE:
            return FreshnessUseDecision.RESTRICTED
        return FreshnessUseDecision.DENIED
    return FreshnessUseDecision.DENIED


def is_prohibited_prediction_use_case(use_case: PredictionUseCase) -> bool:
    return use_case in PROHIBITED_PREDICTION_USE_CASES


def knowledge_policy_decision_permits_definitive_use(
    decision: KnowledgePolicyDecision,
) -> bool:
    return decision is KnowledgePolicyDecision.REQUIRED_FOUND


def policy_outcome_equivalent_to_required_found(outcome: PolicyOutcome) -> bool:
    return False


@dataclass(frozen=True)
class ClinicalJurisdiction:
    scope: ClinicalJurisdictionScope
    country_code: Optional[str] = None
    subdivision_code: Optional[str] = None
    organization_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ClinicalJurisdictionScope):
            raise ValueError("jurisdiction_scope_invalid")
        if self.scope is ClinicalJurisdictionScope.GLOBAL:
            if (
                self.country_code is not None
                or self.subdivision_code is not None
                or self.organization_id is not None
            ):
                raise ValueError("global_jurisdiction_cannot_carry_local_identifiers")
            return
        if self.scope is ClinicalJurisdictionScope.COUNTRY:
            object.__setattr__(
                self,
                "country_code",
                _normalize_iso3166_alpha2(self.country_code or "", "country_code"),
            )
            if self.subdivision_code is not None:
                raise ValueError("country_scope_cannot_carry_subdivision")
            if self.organization_id is not None:
                raise ValueError("country_scope_cannot_carry_organization")
            return
        if self.scope is ClinicalJurisdictionScope.SUBDIVISION:
            object.__setattr__(
                self,
                "country_code",
                _normalize_iso3166_alpha2(self.country_code or "", "country_code"),
            )
            object.__setattr__(
                self,
                "subdivision_code",
                _require_nonempty_str(self.subdivision_code or "", "subdivision_code"),
            )
            if self.organization_id is not None:
                raise ValueError("subdivision_scope_cannot_carry_organization")
            return
        if self.scope is ClinicalJurisdictionScope.ORGANIZATION:
            object.__setattr__(
                self,
                "country_code",
                _normalize_iso3166_alpha2(self.country_code or "", "country_code"),
            )
            if self.subdivision_code is not None:
                object.__setattr__(
                    self,
                    "subdivision_code",
                    _require_nonempty_str(self.subdivision_code, "subdivision_code"),
                )
            object.__setattr__(
                self,
                "organization_id",
                _require_nonempty_str(self.organization_id or "", "organization_id"),
            )
            return
        raise ValueError("jurisdiction_scope_unsupported")


def jurisdiction_applies_to(
    source_jurisdiction: ClinicalJurisdiction,
    requested_jurisdiction: ClinicalJurisdiction,
) -> bool:
    """Directional applicability: whether source may authorize a requested scope."""
    if not isinstance(source_jurisdiction, ClinicalJurisdiction):
        return False
    if not isinstance(requested_jurisdiction, ClinicalJurisdiction):
        return False
    if source_jurisdiction.scope is ClinicalJurisdictionScope.GLOBAL:
        return True
    if requested_jurisdiction.scope is ClinicalJurisdictionScope.GLOBAL:
        return False
    if source_jurisdiction.country_code != requested_jurisdiction.country_code:
        return False
    if source_jurisdiction.scope is ClinicalJurisdictionScope.COUNTRY:
        return requested_jurisdiction.scope in (
            ClinicalJurisdictionScope.COUNTRY,
            ClinicalJurisdictionScope.SUBDIVISION,
            ClinicalJurisdictionScope.ORGANIZATION,
        )
    if source_jurisdiction.scope is ClinicalJurisdictionScope.SUBDIVISION:
        if requested_jurisdiction.scope is ClinicalJurisdictionScope.COUNTRY:
            return False
        if source_jurisdiction.subdivision_code != requested_jurisdiction.subdivision_code:
            return False
        return requested_jurisdiction.scope in (
            ClinicalJurisdictionScope.SUBDIVISION,
            ClinicalJurisdictionScope.ORGANIZATION,
        )
    if source_jurisdiction.scope is ClinicalJurisdictionScope.ORGANIZATION:
        if requested_jurisdiction.scope is not ClinicalJurisdictionScope.ORGANIZATION:
            return False
        if source_jurisdiction.subdivision_code != requested_jurisdiction.subdivision_code:
            return False
        if source_jurisdiction.organization_id is None:
            return False
        if requested_jurisdiction.organization_id is None:
            return False
        return source_jurisdiction.organization_id == requested_jurisdiction.organization_id
    return False


def jurisdictions_compatible(
    left: ClinicalJurisdiction,
    right: ClinicalJurisdiction,
) -> bool:
    """Strict mutual compatibility: each jurisdiction must apply to the other."""
    return jurisdiction_applies_to(left, right) and jurisdiction_applies_to(right, left)


@dataclass(frozen=True)
class ConditionIdentifier:
    taxonomy_authority: str
    namespace: str
    code: str
    jurisdiction: ClinicalJurisdiction
    taxonomy_version: Optional[str] = None

    def __post_init__(self) -> None:
        _require_nonempty_str(self.taxonomy_authority, "taxonomy_authority")
        _require_nonempty_str(self.namespace, "namespace")
        _require_nonempty_str(self.code, "code")
        if self.taxonomy_version is not None:
            _require_nonempty_str(self.taxonomy_version, "taxonomy_version")
        if not isinstance(self.jurisdiction, ClinicalJurisdiction):
            raise ValueError("jurisdiction_invalid")

    @property
    def stable_identifier(self) -> Tuple[str, str, str, Optional[str]]:
        return (
            self.taxonomy_authority,
            self.namespace,
            self.code,
            self.taxonomy_version,
        )


@dataclass(frozen=True)
class ExternalTaxonomyMapping:
    local_condition: ConditionIdentifier
    external_authority: str
    external_namespace: str
    external_code: str
    taxonomy_version: str
    jurisdiction: ClinicalJurisdiction
    relation: TaxonomyMappingRelation
    mapping_evidence_refs: Tuple[str, ...]
    license_status: LicenseStatus
    display_permitted: bool
    storage_permitted: bool
    translation_permitted: bool
    derivative_work_permitted: bool
    redistribution_permitted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.local_condition, ConditionIdentifier):
            raise ValueError("local_condition_invalid")
        _require_nonempty_str(self.external_authority, "external_authority")
        _require_nonempty_str(self.external_namespace, "external_namespace")
        _require_nonempty_str(self.external_code, "external_code")
        _require_nonempty_str(self.taxonomy_version, "taxonomy_version")
        if not isinstance(self.jurisdiction, ClinicalJurisdiction):
            raise ValueError("jurisdiction_invalid")
        if not isinstance(self.relation, TaxonomyMappingRelation):
            raise ValueError("mapping_relation_invalid")
        object.__setattr__(
            self,
            "mapping_evidence_refs",
            _freeze_str_tuple(
                self.mapping_evidence_refs,
                field_name="mapping_evidence_refs",
                allow_empty=False,
            ),
        )
        if not isinstance(self.license_status, LicenseStatus):
            raise ValueError("license_status_invalid")
        if not jurisdiction_applies_to(
            self.local_condition.jurisdiction,
            self.jurisdiction,
        ):
            raise ValueError("mapping_jurisdiction_outside_condition_applicability")

        permissions = (
            self.display_permitted,
            self.storage_permitted,
            self.translation_permitted,
            self.derivative_work_permitted,
            self.redistribution_permitted,
        )
        if self.relation is TaxonomyMappingRelation.UNVERIFIED:
            if any(permissions):
                raise ValueError("unverified_mapping_cannot_permit_any_use")
        if self.license_status in _BLOCKED_LICENSE_STATUSES:
            if any(permissions):
                raise ValueError("blocked_license_cannot_permit_use")
        if self.license_status is LicenseStatus.RESTRICTED:
            if all(permissions):
                raise ValueError("restricted_license_cannot_permit_every_right")


@dataclass(frozen=True)
class LocalizedClinicalTerm:
    language_tag: str
    text: str
    is_preferred: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "language_tag",
            _normalize_bcp47_language_tag(self.language_tag, "language_tag"),
        )
        object.__setattr__(
            self,
            "text",
            _normalize_normalized_term_text(self.text, "text"),
        )
        if not isinstance(self.is_preferred, bool):
            raise ValueError("is_preferred_invalid")

    @property
    def normalized_key(self) -> Tuple[str, str]:
        return (self.language_tag, self.text)


@dataclass(frozen=True)
class ConditionTerminology:
    terms: Tuple[LocalizedClinicalTerm, ...]

    def __post_init__(self) -> None:
        items = tuple(self.terms)
        if len(items) == 0:
            raise ValueError("terms_empty")
        seen: set[Tuple[str, str]] = set()
        preferred_by_language: dict[str, int] = {}
        normalized: list[LocalizedClinicalTerm] = []
        for term in items:
            if not isinstance(term, LocalizedClinicalTerm):
                raise ValueError("term_invalid")
            if term.normalized_key in seen:
                raise ValueError("terms_duplicate")
            seen.add(term.normalized_key)
            if term.is_preferred:
                preferred_by_language[term.language_tag] = (
                    preferred_by_language.get(term.language_tag, 0) + 1
                )
            normalized.append(term)
        if not any(term.is_preferred for term in normalized):
            raise ValueError("preferred_label_required")
        if any(count > 1 for count in preferred_by_language.values()):
            raise ValueError("duplicate_preferred_label")
        object.__setattr__(self, "terms", tuple(normalized))


@dataclass(frozen=True)
class DiseasePackIdentity:
    pack_id: str
    condition: ConditionIdentifier
    knowledge_domain: KnowledgeDomain
    clinical_domain: ClinicalDomain
    disease_system: DiseaseSystem
    pack_version: str
    jurisdiction: ClinicalJurisdiction
    terminology: ConditionTerminology
    disease_group_code: Optional[str] = None

    def __post_init__(self) -> None:
        _require_nonempty_str(self.pack_id, "pack_id")
        if not isinstance(self.condition, ConditionIdentifier):
            raise ValueError("condition_invalid")
        if self.knowledge_domain is not KnowledgeDomain.CLINICAL_DISEASE:
            raise ValueError("disease_pack_requires_clinical_disease_domain")
        if not isinstance(self.clinical_domain, ClinicalDomain):
            raise ValueError("clinical_domain_invalid")
        if not isinstance(self.disease_system, DiseaseSystem):
            raise ValueError("disease_system_invalid")
        _require_nonempty_str(self.pack_version, "pack_version")
        if not isinstance(self.jurisdiction, ClinicalJurisdiction):
            raise ValueError("jurisdiction_invalid")
        if not isinstance(self.terminology, ConditionTerminology):
            raise ValueError("terminology_invalid")
        if self.disease_group_code is not None:
            _require_nonempty_str(self.disease_group_code, "disease_group_code")
        if not jurisdiction_applies_to(self.condition.jurisdiction, self.jurisdiction):
            raise ValueError("condition_pack_jurisdiction_conflict")


@dataclass(frozen=True)
class KnowledgeRequirement:
    knowledge_domain: KnowledgeDomain
    decision: KnowledgePolicyDecision
    required_evidence_facets: Tuple[EvidenceFacet, ...]
    jurisdiction: ClinicalJurisdiction
    citation_required: bool
    reason_codes: Tuple[str, ...]
    evidence_references: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.knowledge_domain, KnowledgeDomain):
            raise ValueError("knowledge_domain_invalid")
        if not isinstance(self.decision, KnowledgePolicyDecision):
            raise ValueError("decision_invalid")
        object.__setattr__(
            self,
            "required_evidence_facets",
            _freeze_evidence_facet_tuple(
                self.required_evidence_facets,
                field_name="required_evidence_facets",
                allow_empty=False,
            ),
        )
        if not isinstance(self.jurisdiction, ClinicalJurisdiction):
            raise ValueError("jurisdiction_invalid")
        if not isinstance(self.citation_required, bool):
            raise ValueError("citation_required_invalid")
        object.__setattr__(
            self,
            "reason_codes",
            _freeze_str_tuple(
                self.reason_codes,
                field_name="reason_codes",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "evidence_references",
            _freeze_str_tuple(
                self.evidence_references,
                field_name="evidence_references",
                allow_empty=True,
            ),
        )
        if self.decision is KnowledgePolicyDecision.REQUIRED_FOUND:
            if len(self.evidence_references) == 0:
                raise ValueError("required_found_requires_evidence")
            if not self.citation_required:
                raise ValueError("required_found_requires_citation")
        if self.decision is KnowledgePolicyDecision.NOT_REQUIRED:
            if len(self.evidence_references) > 0:
                raise ValueError("not_required_cannot_carry_evidence")
        if self.decision is KnowledgePolicyDecision.BLOCKED:
            if len(self.evidence_references) > 0:
                raise ValueError("blocked_cannot_carry_evidence")


@dataclass(frozen=True)
class RollbackTarget:
    approved_baseline_identity: str

    def __post_init__(self) -> None:
        _require_nonempty_str(
            self.approved_baseline_identity,
            "approved_baseline_identity",
        )


@dataclass(frozen=True)
class RollbackRequirement:
    decision: RollbackDecision
    source_artifact_identity: str
    target: Optional[RollbackTarget] = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RollbackDecision):
            raise ValueError("rollback_decision_invalid")
        _require_nonempty_str(self.source_artifact_identity, "source_artifact_identity")
        if self.target is not None and not isinstance(self.target, RollbackTarget):
            raise ValueError("rollback_target_invalid")
        if self.decision in (
            RollbackDecision.REQUIRED,
            RollbackDecision.COMPLETED,
        ):
            if self.target is None:
                raise ValueError("rollback_requires_target")
            if self.target.approved_baseline_identity == self.source_artifact_identity:
                raise ValueError("rollback_target_cannot_equal_source")
        if self.decision is RollbackDecision.BLOCKED_NO_APPROVED_BASELINE:
            if self.target is not None:
                raise ValueError("blocked_rollback_cannot_carry_target")
        if self.decision is RollbackDecision.NOT_REQUIRED:
            if self.target is not None:
                raise ValueError("not_required_rollback_cannot_carry_target")


@dataclass(frozen=True)
class KnowledgePackGovernanceState:
    review_status: ReviewStatus
    publication_state: PublicationState
    freshness_status: FreshnessStatus
    license_status: LicenseStatus
    contradiction_status: ContradictionStatus
    revocation_decision: RevocationDecision
    authority_kind: GovernedAuthorityKind
    jurisdiction: ClinicalJurisdiction
    evidence_criticality: EvidenceCriticality
    high_risk_change: bool
    rollback: Optional[RollbackRequirement] = None

    def __post_init__(self) -> None:
        for field_name, expected_type in (
            ("review_status", ReviewStatus),
            ("publication_state", PublicationState),
            ("freshness_status", FreshnessStatus),
            ("license_status", LicenseStatus),
            ("contradiction_status", ContradictionStatus),
            ("revocation_decision", RevocationDecision),
            ("authority_kind", GovernedAuthorityKind),
            ("evidence_criticality", EvidenceCriticality),
        ):
            if not isinstance(getattr(self, field_name), expected_type):
                raise ValueError(f"{field_name}_invalid")
        if not isinstance(self.jurisdiction, ClinicalJurisdiction):
            raise ValueError("jurisdiction_invalid")
        if not isinstance(self.high_risk_change, bool):
            raise ValueError("high_risk_change_invalid")
        if self.rollback is not None and not isinstance(self.rollback, RollbackRequirement):
            raise ValueError("rollback_invalid")

    def passes_pack_state_prefilter(self) -> bool:
        """Pack-state prefilter only.

        Does not evaluate requested use case, requested jurisdiction, evidence
        facets, knowledge requirement, citation, user-specific prediction
        permission, or final answer permission.
        """
        if self.review_status is not ReviewStatus.APPROVED:
            return False
        if self.publication_state is not PublicationState.PUBLISHED:
            return False
        if self.license_status is not LicenseStatus.EXPLICIT_GRANT:
            return False
        if self.freshness_status is not FreshnessStatus.FRESH:
            return False
        if self.contradiction_status not in (
            ContradictionStatus.NONE,
            ContradictionStatus.RESOLVED_PREFERRED_AUTHORITY,
            ContradictionStatus.RESOLVED_JURISDICTION,
        ):
            return False
        if self.revocation_decision is not RevocationDecision.NOT_REVOKED:
            return False
        if self.rollback is not None and self.rollback.decision in (
            RollbackDecision.REQUIRED,
            RollbackDecision.BLOCKED_NO_APPROVED_BASELINE,
        ):
            return False
        if self.high_risk_change:
            return False
        if self.authority_kind is not GovernedAuthorityKind.CLINICAL_EVIDENCE:
            return False
        return True

    def blocks_any_allowing_decision(self) -> bool:
        """Lifecycle states that forbid every allowing evidence decision."""
        if self.review_status is not ReviewStatus.APPROVED:
            return True
        if self.publication_state is not PublicationState.PUBLISHED:
            return True
        if self.high_risk_change:
            return True
        if self.revocation_decision is not RevocationDecision.NOT_REVOKED:
            return True
        if self.rollback is not None and self.rollback.decision in (
            RollbackDecision.REQUIRED,
            RollbackDecision.BLOCKED_NO_APPROVED_BASELINE,
        ):
            return True
        if self.license_status in _BLOCKED_LICENSE_STATUSES:
            return True
        if self.license_status is LicenseStatus.RESTRICTED:
            return True
        if self.contradiction_status in (
            ContradictionStatus.DETECTED_UNRESOLVED,
            ContradictionStatus.BLOCKED,
        ):
            return True
        return False


@dataclass(frozen=True)
class PredictionUseBoundary:
    use_case: PredictionUseCase
    has_authorized_user_data: bool
    has_provenance: bool
    has_user_consent: bool
    has_sufficient_data: bool
    has_i4_safety_clearance: bool
    has_governed_evidence: bool
    has_uncertainty_representation: bool
    jurisdiction_mismatch: bool
    freshness: FreshnessStatus
    reason_codes: Tuple[PredictionReasonCode, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.use_case, PredictionUseCase):
            raise ValueError("use_case_invalid")
        if not isinstance(self.freshness, FreshnessStatus):
            raise ValueError("freshness_invalid")
        object.__setattr__(
            self,
            "reason_codes",
            _freeze_prediction_reason_tuple(
                self.reason_codes,
                field_name="reason_codes",
                allow_empty=True,
            ),
        )


def evaluate_prediction_use(boundary: PredictionUseBoundary) -> PredictionUseDecision:
    if is_prohibited_prediction_use_case(boundary.use_case):
        return PredictionUseDecision.BLOCKED
    if not boundary.has_authorized_user_data:
        return PredictionUseDecision.REQUIRE_MORE_DATA
    if not boundary.has_provenance:
        return PredictionUseDecision.REQUIRE_MORE_DATA
    if not boundary.has_user_consent:
        return PredictionUseDecision.REQUIRE_CONSENT
    if not boundary.has_sufficient_data:
        return PredictionUseDecision.REQUIRE_MORE_DATA
    if PredictionReasonCode.INSUFFICIENT_DATA in boundary.reason_codes:
        return PredictionUseDecision.REQUIRE_MORE_DATA
    if not boundary.has_i4_safety_clearance:
        return PredictionUseDecision.REQUIRE_HUMAN_REVIEW
    if not boundary.has_governed_evidence:
        return PredictionUseDecision.REQUIRE_MORE_DATA
    if not boundary.has_uncertainty_representation:
        return PredictionUseDecision.REQUIRE_MORE_DATA
    if boundary.jurisdiction_mismatch:
        return PredictionUseDecision.BLOCKED
    if boundary.freshness is FreshnessStatus.HARD_STALE:
        return PredictionUseDecision.BLOCKED
    if boundary.freshness is FreshnessStatus.UNKNOWN_AGE:
        return PredictionUseDecision.BLOCKED
    if boundary.freshness is FreshnessStatus.SOFT_STALE:
        return PredictionUseDecision.REQUIRE_HUMAN_REVIEW
    if len(boundary.reason_codes) == 0:
        return PredictionUseDecision.REQUIRE_MORE_DATA
    return PredictionUseDecision.ALLOW


@dataclass(frozen=True)
class EvidenceUseAssessment:
    """Evidence-use decision bound to pack lifecycle and request context.

    Allowing decisions require full governance binding. Deny/review decisions
    may be constructed with the same fields for auditability.
    """

    decision: EvidenceUseDecision
    pack_state: KnowledgePackGovernanceState
    pack_identity: DiseasePackIdentity
    requested_use: AuthorityUseCase
    requested_jurisdiction: ClinicalJurisdiction
    knowledge_requirement: KnowledgeRequirement
    evidence_criticality: EvidenceCriticality
    evidence_facets: Tuple[EvidenceFacet, ...]
    citation_required: bool
    reason_codes: Tuple[str, ...]
    evidence_references: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, EvidenceUseDecision):
            raise ValueError("decision_invalid")
        if not isinstance(self.pack_state, KnowledgePackGovernanceState):
            raise ValueError("pack_state_required")
        if not isinstance(self.pack_identity, DiseasePackIdentity):
            raise ValueError("pack_identity_required")
        if not isinstance(self.requested_use, AuthorityUseCase):
            raise ValueError("requested_use_invalid")
        if not isinstance(self.requested_jurisdiction, ClinicalJurisdiction):
            raise ValueError("requested_jurisdiction_invalid")
        if not isinstance(self.knowledge_requirement, KnowledgeRequirement):
            raise ValueError("knowledge_requirement_invalid")
        if not isinstance(self.evidence_criticality, EvidenceCriticality):
            raise ValueError("evidence_criticality_invalid")
        object.__setattr__(
            self,
            "evidence_facets",
            _freeze_evidence_facet_tuple(
                self.evidence_facets,
                field_name="evidence_facets",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "reason_codes",
            _freeze_str_tuple(
                self.reason_codes,
                field_name="reason_codes",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "evidence_references",
            _freeze_str_tuple(
                self.evidence_references,
                field_name="evidence_references",
                allow_empty=True,
            ),
        )
        if self.decision not in ALLOWING_EVIDENCE_USE_DECISIONS:
            return
        self._validate_common_allowing_lifecycle()
        if self.decision is EvidenceUseDecision.ALLOW_WITH_CITATION:
            self._validate_unrestricted_allowing_decision()
        elif self.decision is EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS:
            self._validate_restricted_allowing_decision()

    def _validate_common_allowing_lifecycle(self) -> None:
        """Shared fail-closed gate for every allowing evidence decision."""
        if self.pack_state.blocks_any_allowing_decision():
            raise ValueError("lifecycle_blocks_allowing_decision")
        if self.pack_state.review_status is not ReviewStatus.APPROVED:
            raise ValueError("allow_requires_approved_review")
        if self.pack_state.publication_state is not PublicationState.PUBLISHED:
            raise ValueError("allow_requires_published_state")
        if self.pack_state.high_risk_change:
            raise ValueError("high_risk_change_cannot_allow")
        if self.pack_state.revocation_decision is not RevocationDecision.NOT_REVOKED:
            raise ValueError("revocation_blocks_allow")
        if self.pack_state.rollback is not None and self.pack_state.rollback.decision in (
            RollbackDecision.REQUIRED,
            RollbackDecision.BLOCKED_NO_APPROVED_BASELINE,
        ):
            raise ValueError("rollback_blocks_allow")
        if self.pack_state.license_status in _BLOCKED_LICENSE_STATUSES:
            raise ValueError("license_blocks_allow")
        if self.pack_state.license_status is LicenseStatus.RESTRICTED:
            raise ValueError("restricted_license_cannot_allow")
        if (
            evaluate_authority_separation(
                self.pack_state.authority_kind,
                self.requested_use,
            )
            is not AuthoritySeparationOutcome.PERMITTED
        ):
            raise ValueError("authority_use_mismatch")
        if not jurisdiction_applies_to(
            self.pack_state.jurisdiction,
            self.requested_jurisdiction,
        ):
            raise ValueError("evidence_jurisdiction_mismatch")
        if self.pack_identity.clinical_domain is ClinicalDomain.UNKNOWN:
            raise ValueError("unknown_clinical_domain_cannot_allow")
        if self.pack_identity.disease_system is DiseaseSystem.UNKNOWN:
            raise ValueError("unknown_disease_system_cannot_allow")
        if self.knowledge_requirement.decision is not KnowledgePolicyDecision.REQUIRED_FOUND:
            raise ValueError("allow_requires_required_found")
        required_facets = set(self.knowledge_requirement.required_evidence_facets)
        available_facets = set(self.evidence_facets)
        if not required_facets.issubset(available_facets):
            raise ValueError("required_evidence_facets_missing")
        if len(self.evidence_references) == 0:
            raise ValueError("allow_requires_evidence")
        required_refs = set(self.knowledge_requirement.evidence_references)
        available_refs = set(self.evidence_references)
        if not required_refs.issubset(available_refs):
            raise ValueError("evidence_references_incomplete")
        if (
            self.pack_identity.knowledge_domain is KnowledgeDomain.CLINICAL_DISEASE
            and not self.citation_required
        ):
            raise ValueError("clinical_allow_requires_citation")
        if self.knowledge_requirement.citation_required and not self.citation_required:
            raise ValueError("requirement_citation_not_satisfied")

    def _validate_unrestricted_allowing_decision(self) -> None:
        """ALLOW_WITH_CITATION: shared lifecycle plus full unrestricted pack state."""
        if not self.pack_state.passes_pack_state_prefilter():
            raise ValueError("unrestricted_allow_requires_pack_prefilter")
        if self.pack_state.license_status is not LicenseStatus.EXPLICIT_GRANT:
            raise ValueError("unrestricted_allow_requires_explicit_grant")
        if self.pack_state.freshness_status is not FreshnessStatus.FRESH:
            raise ValueError("unrestricted_allow_requires_fresh")
        if self.pack_state.contradiction_status not in (
            ContradictionStatus.NONE,
            ContradictionStatus.RESOLVED_PREFERRED_AUTHORITY,
            ContradictionStatus.RESOLVED_JURISDICTION,
        ):
            raise ValueError("unrestricted_allow_requires_resolved_contradiction")
        freshness_outcome = evaluate_freshness_criticality_use(
            self.evidence_criticality,
            self.pack_state.freshness_status,
        )
        if freshness_outcome is not FreshnessUseDecision.ELIGIBLE:
            raise ValueError("unrestricted_allow_requires_fresh_eligible")

    def _validate_restricted_allowing_decision(self) -> None:
        """ALLOW_WITH_RESTRICTIONS: shared lifecycle plus supported restricted conditions."""
        if self.pack_state.license_status is not LicenseStatus.EXPLICIT_GRANT:
            raise ValueError("restricted_allow_requires_explicit_grant")
        if self.pack_state.contradiction_status in (
            ContradictionStatus.DETECTED_UNRESOLVED,
            ContradictionStatus.BLOCKED,
        ):
            raise ValueError("contradiction_blocks_allow")
        if self.pack_state.contradiction_status not in (
            ContradictionStatus.NONE,
            ContradictionStatus.RESOLVED_PREFERRED_AUTHORITY,
            ContradictionStatus.RESOLVED_JURISDICTION,
            ContradictionStatus.ACCEPTED_DIVERGENCE,
        ):
            raise ValueError("contradiction_blocks_allow")
        if self.pack_state.freshness_status in (
            FreshnessStatus.HARD_STALE,
            FreshnessStatus.UNKNOWN_AGE,
        ):
            raise ValueError("freshness_blocks_allow")
        freshness_outcome = evaluate_freshness_criticality_use(
            self.evidence_criticality,
            self.pack_state.freshness_status,
        )
        if freshness_outcome is FreshnessUseDecision.DENIED:
            raise ValueError("freshness_blocks_allow")
        if (
            self.pack_state.freshness_status is FreshnessStatus.SOFT_STALE
            and freshness_outcome is not FreshnessUseDecision.RESTRICTED
        ):
            raise ValueError("soft_stale_requires_restricted_freshness_outcome")
