"""Section 15-I5-B2-P1 — governed source profile persistence (deterministic, no I/O).

No network, HTTP, filesystem, scheduler, publication, LLM, RAG, or public API.
Legacy companion seed is deferred to 15-I5-B2-P1-L1.

Transaction contract:
- Caller owns the outer Session commit/rollback.
- This module never commits.
- Normal approved service writers serialize on the profile row (FOR UPDATE).
  A second compliant append usually resolves during the same-fingerprint
  pre-check (idempotent Case A / fail-closed Case B) and does not reach
  IntegrityError.
- The savepoint recovery path is a final defense for exact same-profile,
  same-fingerprint uniqueness races caused by bypassing or external writers
  (direct SQL / unsupported ORM / visibility outside the approved boundary).
  Database uniqueness remains the final invariant.
- Recoverable same-fingerprint races use a nested savepoint only; the outer
  session remains usable after savepoint rollback. There is no full outer
  rollback and no automatic retry loop inside this module.
- Unrelated IntegrityError values are mapped to typed fail-closed errors
  (or re-raised) without querying on a failed transaction.
- Immutable versions are protected at the approved persistence service
  boundary only. There is no DB trigger; direct ORM/SQL UPDATE remains
  outside the supported contract.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import GovernedSourceProfile, GovernedSourceProfileVersion
from backend.app.services.governance.contracts import (
    AutomationStatus,
    AuthorityTier,
    ClinicalJurisdictionScope,
    FailClosedDefaults,
    FreshnessStatus,
    LicenseStatus,
    PermissionDecision,
    SourceClass,
    SourceOperationalStatus,
    VerificationMethod,
)

SNAPSHOT_SCHEMA_VERSION: str = "i5b2_p1_v1"
_SHA256_HEX_LEN: int = 64
_INITIAL_ROW_VERSION: int = 1
_INITIAL_VERSION_SEQ: int = 1
_URL_LOCATOR_KINDS = frozenset({"url", "canonical_url", "https", "http"})

_FAIL_CLOSED = FailClosedDefaults()
DEFAULT_OPERATIONAL_STATUS: str = _FAIL_CLOSED.operational_status.value

REASON_EXISTING_FINGERPRINT_IS_NOT_CURRENT = "existing_fingerprint_is_not_current"
REASON_SUPERSEDES_CYCLE = "supersedes_cycle_detected"
REASON_SUPERSEDES_SELF = "supersedes_self_forbidden"
REASON_LOCATOR_URL_INVALID = "locator_url_invalid"


class SourceProfilePersistenceError(ValueError):
    """Fail-closed persistence boundary error with a stable reason code."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class GovernanceEvidenceSnapshot:
    """Explicit typed governance evidence for an immutable profile version."""

    publisher_authority_identity: str
    source_class: str
    authority_evidence_tier: str
    jurisdiction_scope: str
    jurisdiction_country_code: Optional[str]
    jurisdiction_subdivision_code: Optional[str]
    jurisdiction_organization_id: Optional[str]
    primary_language: str
    specialty_domain: str
    license_status: str
    permitted_use_restriction: str
    storage_permission: str
    transformation_permission: str
    display_redistribution_permission: str
    automation_status: str
    verification_method: str
    freshness_policy_days: int
    freshness_status: str
    fetch_policy: str
    iran_first_applicable: bool
    policy_version_reference: str
    configuration_version_reference: str
    effective_at: datetime


_FINGERPRINT_FIELD_ORDER: Tuple[str, ...] = (
    "snapshot_schema_version",
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
    "effective_at",
)


def _nfc_strip(value: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFC", value).strip()


def normalize_canonical_key(raw: Any) -> str:
    """Trim, NFC, casefold; reject empty. Deterministic identity key."""
    if not isinstance(raw, str):
        raise SourceProfilePersistenceError("canonical_key_invalid_type")
    normalized = _nfc_strip(raw).casefold()
    if not normalized:
        raise SourceProfilePersistenceError("canonical_key_empty")
    return normalized


def _normalize_url_locator(loc: str) -> str:
    """Deterministic URL identity without DNS, redirects, or path casefolding.

    Host policy:
    - DNS hostname: deterministic IDNA encode + casefold; preserve explicit port.
    - IPv4/IPv6 literals: ipaddress canonical form; no IDNA; IPv6 bracketed.
    """
    try:
        parts = urlsplit(loc)
        # .port / .hostname may raise ValueError for malformed netloc/port/IPv6.
        port = parts.port
        hostname = parts.hostname
        username = parts.username
        password = parts.password
    except ValueError as exc:
        raise SourceProfilePersistenceError(REASON_LOCATOR_URL_INVALID) from exc

    if username is not None or password is not None:
        raise SourceProfilePersistenceError("locator_credentials_forbidden")
    scheme = (parts.scheme or "").casefold()
    if not scheme:
        raise SourceProfilePersistenceError("locator_url_scheme_required")
    if hostname is None or not hostname:
        raise SourceProfilePersistenceError("locator_url_host_required")

    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            host = hostname.encode("idna").decode("ascii").casefold()
        except (UnicodeError, ValueError) as exc:
            raise SourceProfilePersistenceError(REASON_LOCATOR_URL_INVALID) from exc
        netloc = host
    else:
        if isinstance(ip_obj, ipaddress.IPv6Address):
            netloc = f"[{ip_obj.compressed}]"
        else:
            netloc = ip_obj.compressed

    if port is not None:
        netloc = f"{netloc}:{port}"

    # Preserve path / query / fragment bytes exactly (no casefold, no slash policy).
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))


def normalize_locator(
    locator_kind: Any,
    locator: Any,
) -> Tuple[Optional[str], Optional[str]]:
    """Normalize optional locator pair. Both absent or both present.

    Reason contract:
    - kind present + locator is None → locator_required_when_locator_kind_present
    - kind present + locator is blank string → locator_empty
    - locator present + kind missing → locator_kind_required_when_locator_present
    """
    kind_absent = locator_kind is None or (
        isinstance(locator_kind, str) and not locator_kind.strip()
    )
    loc_is_none = locator is None
    loc_is_blank_str = isinstance(locator, str) and not locator.strip()

    if kind_absent and (loc_is_none or loc_is_blank_str):
        return None, None
    if kind_absent:
        raise SourceProfilePersistenceError("locator_kind_required_when_locator_present")
    if loc_is_none:
        raise SourceProfilePersistenceError("locator_required_when_locator_kind_present")
    if not isinstance(locator_kind, str):
        raise SourceProfilePersistenceError("locator_kind_invalid_type")
    if not isinstance(locator, str):
        raise SourceProfilePersistenceError("locator_invalid_type")
    if loc_is_blank_str:
        raise SourceProfilePersistenceError("locator_empty")
    kind = _nfc_strip(locator_kind).casefold()
    loc = _nfc_strip(locator)
    if not kind:
        raise SourceProfilePersistenceError("locator_kind_empty")
    if not loc:
        raise SourceProfilePersistenceError("locator_empty")
    if kind in _URL_LOCATOR_KINDS:
        loc = _normalize_url_locator(loc)
    else:
        # Non-URL kinds: NFC + trim only (no URL semantics).
        loc = _nfc_strip(loc)
        if not loc:
            raise SourceProfilePersistenceError("locator_empty")
    return kind, loc


def _require_enum_str(field: str, value: Any, enum_cls: type[Enum]) -> str:
    if isinstance(value, enum_cls):
        return value.value
    if not isinstance(value, str):
        raise SourceProfilePersistenceError(f"{field}_invalid_type")
    text = _nfc_strip(value)
    if not text:
        raise SourceProfilePersistenceError(f"{field}_empty")
    try:
        return enum_cls(text).value
    except ValueError as exc:
        raise SourceProfilePersistenceError(f"{field}_unsupported") from exc


def _require_nonempty_str(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise SourceProfilePersistenceError(f"{field}_invalid_type")
    text = _nfc_strip(value)
    if not text:
        raise SourceProfilePersistenceError(f"{field}_empty")
    return text


def _require_bool(field: str, value: Any) -> bool:
    if type(value) is not bool:
        raise SourceProfilePersistenceError(f"{field}_must_be_bool")
    return value


def _require_int(field: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourceProfilePersistenceError(f"{field}_must_be_int")
    return value


def _require_aware_datetime(field: str, value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise SourceProfilePersistenceError(f"{field}_invalid_type")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise SourceProfilePersistenceError(f"{field}_naive_datetime_forbidden")
    return value.astimezone(timezone.utc)


def coerce_governance_evidence(raw: Mapping[str, Any]) -> GovernanceEvidenceSnapshot:
    """Validate and normalize explicit governance evidence into a typed snapshot."""
    if not isinstance(raw, Mapping):
        raise SourceProfilePersistenceError("governance_evidence_must_be_mapping")

    def get(name: str) -> Any:
        if name not in raw:
            raise SourceProfilePersistenceError(f"{name}_required")
        return raw[name]

    scope = _require_enum_str(
        "jurisdiction_scope", get("jurisdiction_scope"), ClinicalJurisdictionScope
    )
    country = get("jurisdiction_country_code")
    subdivision = get("jurisdiction_subdivision_code")
    organization = get("jurisdiction_organization_id")
    if country is not None:
        country = _require_nonempty_str("jurisdiction_country_code", country).upper()
    if subdivision is not None:
        subdivision = _require_nonempty_str("jurisdiction_subdivision_code", subdivision)
    if organization is not None:
        organization = _require_nonempty_str("jurisdiction_organization_id", organization)

    if scope == ClinicalJurisdictionScope.GLOBAL.value:
        if country is not None or subdivision is not None or organization is not None:
            raise SourceProfilePersistenceError("jurisdiction_global_must_omit_parts")
    elif scope == ClinicalJurisdictionScope.COUNTRY.value:
        if country is None:
            raise SourceProfilePersistenceError("jurisdiction_country_required")
        if subdivision is not None or organization is not None:
            raise SourceProfilePersistenceError("jurisdiction_country_must_omit_lower_parts")
    elif scope == ClinicalJurisdictionScope.SUBDIVISION.value:
        if country is None or subdivision is None:
            raise SourceProfilePersistenceError("jurisdiction_subdivision_parts_required")
        if organization is not None:
            raise SourceProfilePersistenceError("jurisdiction_subdivision_must_omit_org")
    elif scope == ClinicalJurisdictionScope.ORGANIZATION.value:
        if country is None or organization is None:
            raise SourceProfilePersistenceError("jurisdiction_organization_parts_required")

    return GovernanceEvidenceSnapshot(
        publisher_authority_identity=_require_nonempty_str(
            "publisher_authority_identity", get("publisher_authority_identity")
        ),
        source_class=_require_enum_str("source_class", get("source_class"), SourceClass),
        authority_evidence_tier=_require_enum_str(
            "authority_evidence_tier", get("authority_evidence_tier"), AuthorityTier
        ),
        jurisdiction_scope=scope,
        jurisdiction_country_code=country,
        jurisdiction_subdivision_code=subdivision,
        jurisdiction_organization_id=organization,
        primary_language=_require_nonempty_str(
            "primary_language", get("primary_language")
        ).casefold(),
        specialty_domain=_require_nonempty_str(
            "specialty_domain", get("specialty_domain")
        ),
        license_status=_require_enum_str(
            "license_status", get("license_status"), LicenseStatus
        ),
        permitted_use_restriction=_require_nonempty_str(
            "permitted_use_restriction", get("permitted_use_restriction")
        ),
        storage_permission=_require_enum_str(
            "storage_permission", get("storage_permission"), PermissionDecision
        ),
        transformation_permission=_require_enum_str(
            "transformation_permission",
            get("transformation_permission"),
            PermissionDecision,
        ),
        display_redistribution_permission=_require_enum_str(
            "display_redistribution_permission",
            get("display_redistribution_permission"),
            PermissionDecision,
        ),
        automation_status=_require_enum_str(
            "automation_status", get("automation_status"), AutomationStatus
        ),
        verification_method=_require_enum_str(
            "verification_method", get("verification_method"), VerificationMethod
        ),
        freshness_policy_days=_require_int(
            "freshness_policy_days", get("freshness_policy_days")
        ),
        freshness_status=_require_enum_str(
            "freshness_status", get("freshness_status"), FreshnessStatus
        ),
        fetch_policy=_require_nonempty_str("fetch_policy", get("fetch_policy")),
        iran_first_applicable=_require_bool(
            "iran_first_applicable", get("iran_first_applicable")
        ),
        policy_version_reference=_require_nonempty_str(
            "policy_version_reference", get("policy_version_reference")
        ),
        configuration_version_reference=_require_nonempty_str(
            "configuration_version_reference", get("configuration_version_reference")
        ),
        effective_at=_require_aware_datetime("effective_at", get("effective_at")),
    )


def _canonical_null() -> str:
    return "__CANONICAL_NULL__"


def _canonical_utc_instant(value: datetime) -> str:
    """Aware→UTC ISO-8601 with exactly six microsecond digits and trailing Z."""
    utc = value.astimezone(timezone.utc)
    # isoformat(timespec='microseconds') yields +00:00; replace with Z.
    text = utc.isoformat(timespec="microseconds")
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    raise SourceProfilePersistenceError("fingerprint_utc_serialization_invalid")


def _fingerprint_scalar(value: Any) -> Any:
    if value is None:
        return _canonical_null()
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return _canonical_utc_instant(value)
    raise SourceProfilePersistenceError("fingerprint_unsupported_scalar")


def canonicalize_governance_evidence(
    evidence: GovernanceEvidenceSnapshot,
    *,
    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> str:
    """Deterministic compact JSON array of [name, value] pairs for fingerprinting."""
    import json

    values = {
        "snapshot_schema_version": snapshot_schema_version,
        "publisher_authority_identity": evidence.publisher_authority_identity,
        "source_class": evidence.source_class,
        "authority_evidence_tier": evidence.authority_evidence_tier,
        "jurisdiction_scope": evidence.jurisdiction_scope,
        "jurisdiction_country_code": evidence.jurisdiction_country_code,
        "jurisdiction_subdivision_code": evidence.jurisdiction_subdivision_code,
        "jurisdiction_organization_id": evidence.jurisdiction_organization_id,
        "primary_language": evidence.primary_language,
        "specialty_domain": evidence.specialty_domain,
        "license_status": evidence.license_status,
        "permitted_use_restriction": evidence.permitted_use_restriction,
        "storage_permission": evidence.storage_permission,
        "transformation_permission": evidence.transformation_permission,
        "display_redistribution_permission": evidence.display_redistribution_permission,
        "automation_status": evidence.automation_status,
        "verification_method": evidence.verification_method,
        "freshness_policy_days": evidence.freshness_policy_days,
        "freshness_status": evidence.freshness_status,
        "fetch_policy": evidence.fetch_policy,
        "iran_first_applicable": evidence.iran_first_applicable,
        "policy_version_reference": evidence.policy_version_reference,
        "configuration_version_reference": evidence.configuration_version_reference,
        "effective_at": evidence.effective_at,
    }
    pairs = [[name, _fingerprint_scalar(values[name])] for name in _FINGERPRINT_FIELD_ORDER]
    return json.dumps(pairs, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def compute_snapshot_fingerprint(
    evidence: GovernanceEvidenceSnapshot,
    *,
    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> str:
    payload = canonicalize_governance_evidence(
        evidence, snapshot_schema_version=snapshot_schema_version
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    if len(digest) != _SHA256_HEX_LEN:
        raise SourceProfilePersistenceError("snapshot_fingerprint_length_invalid")
    return digest


def _assert_supersedes_safe(
    session: Session,
    *,
    profile_id: int,
    supersedes_version_id: int,
) -> None:
    """Same-profile, no self, multi-hop cycle fail-closed (service-enforced)."""
    prior = session.get(GovernedSourceProfileVersion, supersedes_version_id)
    if prior is None or prior.profile_id != profile_id:
        raise SourceProfilePersistenceError("supersedes_version_not_found")

    version_count = (
        session.query(GovernedSourceProfileVersion.id)
        .filter(GovernedSourceProfileVersion.profile_id == profile_id)
        .count()
    )
    bound = int(version_count) + 1
    visited: set[int] = set()
    cursor: Optional[int] = supersedes_version_id
    steps = 0
    while cursor is not None:
        if cursor in visited:
            raise SourceProfilePersistenceError(REASON_SUPERSEDES_CYCLE)
        visited.add(cursor)
        steps += 1
        if steps > bound:
            raise SourceProfilePersistenceError(REASON_SUPERSEDES_CYCLE)
        row = session.get(GovernedSourceProfileVersion, cursor)
        if row is None or row.profile_id != profile_id:
            raise SourceProfilePersistenceError("supersedes_chain_corrupted")
        if row.supersedes_version_id is not None and row.supersedes_version_id == row.id:
            raise SourceProfilePersistenceError(REASON_SUPERSEDES_SELF)
        cursor = row.supersedes_version_id


def _apply_existing_fingerprint_pointer_policy(
    session: Session,
    *,
    profile: GovernedSourceProfile,
    matched: GovernedSourceProfileVersion,
) -> GovernedSourceProfileVersion:
    """Cases A/B/C for existing same-profile fingerprint (no silent rollback)."""
    current_id = profile.current_profile_version_id
    if current_id == matched.id:
        # Case A: already current — pure no-op.
        return matched
    if current_id is not None:
        # Case B: another version is current — fail closed.
        raise SourceProfilePersistenceError(REASON_EXISTING_FINGERPRINT_IS_NOT_CURRENT)

    # Case C: null pointer — initialize only if matched is latest by version_seq.
    max_seq = (
        session.query(GovernedSourceProfileVersion.version_seq)
        .filter(GovernedSourceProfileVersion.profile_id == profile.id)
        .order_by(GovernedSourceProfileVersion.version_seq.desc())
        .limit(1)
        .scalar()
    )
    if max_seq is None or int(matched.version_seq) != int(max_seq):
        raise SourceProfilePersistenceError(REASON_EXISTING_FINGERPRINT_IS_NOT_CURRENT)
    profile.current_profile_version_id = matched.id
    profile.row_version = int(profile.row_version) + 1
    profile.updated_at = datetime.utcnow()
    session.flush()
    return matched


def create_or_get_profile(
    session: Session,
    *,
    canonical_key: Any,
    locator_kind: Any = None,
    locator: Any = None,
    legacy_knowledge_source_id: Any = None,
) -> GovernedSourceProfile:
    """Create a fail-closed profile or return the exact equivalent identity."""
    key = normalize_canonical_key(canonical_key)
    kind, loc = normalize_locator(locator_kind, locator)

    if legacy_knowledge_source_id is not None:
        if isinstance(legacy_knowledge_source_id, bool) or not isinstance(
            legacy_knowledge_source_id, int
        ):
            raise SourceProfilePersistenceError("legacy_knowledge_source_id_must_be_int")
        if legacy_knowledge_source_id <= 0:
            raise SourceProfilePersistenceError("legacy_knowledge_source_id_invalid")

    existing = (
        session.query(GovernedSourceProfile)
        .filter(GovernedSourceProfile.canonical_key == key)
        .one_or_none()
    )
    if existing is not None:
        if (
            existing.locator_kind != kind
            or existing.normalized_locator != loc
            or existing.legacy_knowledge_source_id != legacy_knowledge_source_id
        ):
            raise SourceProfilePersistenceError("canonical_key_identity_conflict")
        return existing

    if kind is not None and loc is not None:
        locator_hit = (
            session.query(GovernedSourceProfile)
            .filter(
                GovernedSourceProfile.locator_kind == kind,
                GovernedSourceProfile.normalized_locator == loc,
            )
            .one_or_none()
        )
        if locator_hit is not None:
            raise SourceProfilePersistenceError("locator_identity_conflict")

    if legacy_knowledge_source_id is not None:
        legacy_hit = (
            session.query(GovernedSourceProfile)
            .filter(
                GovernedSourceProfile.legacy_knowledge_source_id
                == legacy_knowledge_source_id
            )
            .one_or_none()
        )
        if legacy_hit is not None:
            raise SourceProfilePersistenceError("legacy_knowledge_source_conflict")

    profile = GovernedSourceProfile(
        canonical_key=key,
        locator_kind=kind,
        normalized_locator=loc,
        legacy_knowledge_source_id=legacy_knowledge_source_id,
        current_profile_version_id=None,
        operational_status=DEFAULT_OPERATIONAL_STATUS,
        row_version=_INITIAL_ROW_VERSION,
    )
    if profile.operational_status == SourceOperationalStatus.ENABLED_IDLE.value:
        raise SourceProfilePersistenceError("fetch_enabled_default_forbidden")

    session.add(profile)
    try:
        session.flush()
    except IntegrityError as exc:
        raise SourceProfilePersistenceError("profile_identity_integrity_conflict") from exc
    return profile


def get_profile(session: Session, profile_id: int) -> GovernedSourceProfile:
    if isinstance(profile_id, bool) or not isinstance(profile_id, int):
        raise SourceProfilePersistenceError("profile_id_must_be_int")
    profile = session.get(GovernedSourceProfile, profile_id)
    if profile is None:
        raise SourceProfilePersistenceError("profile_not_found")
    return profile


def get_profile_by_canonical_key(
    session: Session, canonical_key: Any
) -> GovernedSourceProfile:
    key = normalize_canonical_key(canonical_key)
    profile = (
        session.query(GovernedSourceProfile)
        .filter(GovernedSourceProfile.canonical_key == key)
        .one_or_none()
    )
    if profile is None:
        raise SourceProfilePersistenceError("profile_not_found")
    return profile


def get_exact_profile_version(
    session: Session, *, profile_id: int, version_id: int
) -> GovernedSourceProfileVersion:
    profile = get_profile(session, profile_id)
    version = session.get(GovernedSourceProfileVersion, version_id)
    if version is None or version.profile_id != profile.id:
        raise SourceProfilePersistenceError("profile_version_not_found")
    return version


def get_current_profile_version(
    session: Session, *, profile_id: int, required: bool = True
) -> Optional[GovernedSourceProfileVersion]:
    profile = get_profile(session, profile_id)
    if profile.current_profile_version_id is None:
        if required:
            raise SourceProfilePersistenceError("current_profile_version_missing")
        return None
    return get_exact_profile_version(
        session,
        profile_id=profile.id,
        version_id=profile.current_profile_version_id,
    )


def append_profile_version(
    session: Session,
    *,
    profile_id: int,
    governance_evidence: Mapping[str, Any],
    expected_row_version: Optional[int] = None,
    expected_current_version_id: Optional[int] = None,
    supersedes_version_id: Optional[int] = None,
    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> GovernedSourceProfileVersion:
    """Append an immutable version and atomically advance the current pointer.

    Caller owns outer commit/rollback. This function never commits and never
    full-rolls-back the outer session.

    Normal approved writers serialize on the profile row. The nested savepoint
    IntegrityError path is a final defense for exact same-profile,
    same-fingerprint uniqueness races from bypassing/external writers — not the
    expected path for two compliant service callers.
    """
    if not isinstance(snapshot_schema_version, str) or not snapshot_schema_version.strip():
        raise SourceProfilePersistenceError("snapshot_schema_version_empty")

    evidence = coerce_governance_evidence(governance_evidence)
    fingerprint = compute_snapshot_fingerprint(
        evidence, snapshot_schema_version=snapshot_schema_version
    )

    profile = (
        session.query(GovernedSourceProfile)
        .filter(GovernedSourceProfile.id == profile_id)
        .with_for_update()
        .one_or_none()
    )
    if profile is None:
        raise SourceProfilePersistenceError("profile_not_found")

    if expected_row_version is not None:
        if isinstance(expected_row_version, bool) or not isinstance(
            expected_row_version, int
        ):
            raise SourceProfilePersistenceError("expected_row_version_must_be_int")
        if profile.row_version != expected_row_version:
            raise SourceProfilePersistenceError("stale_row_version")

    if expected_current_version_id is not None:
        if isinstance(expected_current_version_id, bool) or not isinstance(
            expected_current_version_id, int
        ):
            raise SourceProfilePersistenceError("expected_current_version_id_must_be_int")
        if profile.current_profile_version_id != expected_current_version_id:
            raise SourceProfilePersistenceError("stale_current_version")

    if supersedes_version_id is not None:
        if isinstance(supersedes_version_id, bool) or not isinstance(
            supersedes_version_id, int
        ):
            raise SourceProfilePersistenceError("supersedes_version_id_must_be_int")
        _assert_supersedes_safe(
            session, profile_id=profile.id, supersedes_version_id=supersedes_version_id
        )

    existing_fp = (
        session.query(GovernedSourceProfileVersion)
        .filter(
            GovernedSourceProfileVersion.profile_id == profile.id,
            GovernedSourceProfileVersion.snapshot_fingerprint == fingerprint,
        )
        .one_or_none()
    )
    if existing_fp is not None:
        return _apply_existing_fingerprint_pointer_policy(
            session, profile=profile, matched=existing_fp
        )

    max_seq = (
        session.query(GovernedSourceProfileVersion.version_seq)
        .filter(GovernedSourceProfileVersion.profile_id == profile.id)
        .order_by(GovernedSourceProfileVersion.version_seq.desc())
        .limit(1)
        .scalar()
    )
    next_seq = _INITIAL_VERSION_SEQ if max_seq is None else int(max_seq) + 1

    version = GovernedSourceProfileVersion(
        profile_id=profile.id,
        version_seq=next_seq,
        supersedes_version_id=supersedes_version_id,
        snapshot_schema_version=snapshot_schema_version,
        snapshot_fingerprint=fingerprint,
        effective_at=evidence.effective_at.replace(tzinfo=None),
        publisher_authority_identity=evidence.publisher_authority_identity,
        source_class=evidence.source_class,
        authority_evidence_tier=evidence.authority_evidence_tier,
        jurisdiction_scope=evidence.jurisdiction_scope,
        jurisdiction_country_code=evidence.jurisdiction_country_code,
        jurisdiction_subdivision_code=evidence.jurisdiction_subdivision_code,
        jurisdiction_organization_id=evidence.jurisdiction_organization_id,
        primary_language=evidence.primary_language,
        specialty_domain=evidence.specialty_domain,
        license_status=evidence.license_status,
        permitted_use_restriction=evidence.permitted_use_restriction,
        storage_permission=evidence.storage_permission,
        transformation_permission=evidence.transformation_permission,
        display_redistribution_permission=evidence.display_redistribution_permission,
        automation_status=evidence.automation_status,
        verification_method=evidence.verification_method,
        freshness_policy_days=evidence.freshness_policy_days,
        freshness_status=evidence.freshness_status,
        fetch_policy=evidence.fetch_policy,
        iran_first_applicable=evidence.iran_first_applicable,
        policy_version_reference=evidence.policy_version_reference,
        configuration_version_reference=evidence.configuration_version_reference,
    )

    try:
        with session.begin_nested():
            session.add(version)
            session.flush()
            if version.supersedes_version_id is not None and (
                version.supersedes_version_id == version.id
            ):
                raise SourceProfilePersistenceError(REASON_SUPERSEDES_SELF)
    except SourceProfilePersistenceError:
        raise
    except IntegrityError as exc:
        # Nested savepoint rolled back; outer session remains usable.
        raced = (
            session.query(GovernedSourceProfileVersion)
            .filter(
                GovernedSourceProfileVersion.profile_id == profile.id,
                GovernedSourceProfileVersion.snapshot_fingerprint == fingerprint,
            )
            .one_or_none()
        )
        if raced is not None:
            return _apply_existing_fingerprint_pointer_policy(
                session, profile=profile, matched=raced
            )
        raise SourceProfilePersistenceError("version_integrity_conflict") from exc

    if version.profile_id != profile.id:
        raise SourceProfilePersistenceError("cross_profile_version_forbidden")

    profile.current_profile_version_id = version.id
    profile.row_version = int(profile.row_version) + 1
    profile.updated_at = datetime.utcnow()
    try:
        session.flush()
    except IntegrityError as exc:
        raise SourceProfilePersistenceError("current_pointer_integrity_conflict") from exc
    return version


def reject_immutable_version_mutation(*_args: Any, **_kwargs: Any) -> None:
    """Reject updates through the approved persistence boundary.

    Immutable through approved persistence service boundary.
    No DB trigger. Direct ORM/SQL mutation remains outside supported contract.
    """
    raise SourceProfilePersistenceError("immutable_profile_version_update_forbidden")


def assert_no_legacy_seed_in_p1() -> None:
    """Documented guard: P1 never seeds legacy companions."""
    raise SourceProfilePersistenceError("legacy_seed_deferred_to_p1_l1")


def profile_is_fetch_eligible(profile: GovernedSourceProfile) -> bool:
    """Fetch eligibility uses exact I5 SourceOperationalStatus.ENABLED_IDLE only."""
    return profile.operational_status == SourceOperationalStatus.ENABLED_IDLE.value
