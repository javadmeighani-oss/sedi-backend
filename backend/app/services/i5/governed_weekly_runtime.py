"""I5-IMPL-W6-P01 — governed weekly runtime bridge (Master Gate).

Narrow composition helper for:
- deterministic weekly window / advisory-lock dedupe;
- DB-backed controlled NHS candidate loading;
- authorized raw / KU / provenance persistence;
- idempotent NHS sleep source activation;
- one shared top-level callable for APScheduler, CI, and one-shot proof.

Does not invent schema, parallel crawler architecture, or medical approval.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

import pytz
from sqlalchemy import or_, text

from backend.app.services.governance import kb_b2_source_profile_persistence as gsp_persist
from backend.app.services.governance.contracts import (
    AutomationStatus,
    AuthorityTier,
    ClinicalJurisdictionScope,
    FreshnessStatus,
    LicenseStatus,
    PermissionDecision,
    SourceClass,
    SourceOperationalStatus,
    VerificationMethod,
)
from backend.app.services.i5 import knowledge_memory_service as mem_svc
from backend.app.services.i5 import knowledge_unit_service as ku_svc
from backend.app.services.i5 import provenance_service as prov_svc
from backend.app.services.i5 import supersession_service as sup_svc
from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    MemoryChangeKind,
    PublicationState,
    RawRetentionMode,
    RawStorageMode,
    ReviewState,
    RightsTermsState,
    RobotsAccessState,
)
from backend.app.services.i5.medical_safety_gate import (
    assert_allowed_medical_safety_transition,
    requires_human_review,
)
from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility
from backend.app.services.i5.governed_ku_serving import apply_governed_finalize_and_lexical_index
from backend.app.services.i5.trusted_source_manifest import manifest_attribution
from backend.app.services.i5.source_discovery import (
    SourceCandidateDescriptor,
    map_gsp_row_to_descriptor,
)
from backend.app.services.i5.weekly_orchestrator import (
    SOURCE_ACTIVATION_ENV,
    WEEKLY_ORCHESTRATOR_ENABLE_ENV,
    WEEKLY_ORCHESTRATOR_JOB_ID,
    WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
    OrchestrationOutcome,
    WeeklyOrchestratorError,
    compute_logical_run_key,
    run_dormant_scheduled_tick,
    utc_now,
)

PACKAGE_ID = "I5-IMPL-W6-P01"
NHS_SOURCE_KEY = "nhs_uk_live_well"
NHS_PAGE_KEY = "nhs_sleep"
NHS_SLEEP_URL = "https://www.nhs.uk/live-well/sleep-and-tiredness/"
NHS_ALLOWED_DOMAIN = "nhs.uk"
NHS_ALLOWED_URL_PATTERN = r"^https://www\.nhs\.uk/live-well/.*"
NHS_TRUST_LEVEL = "official"
NHS_ATTRIBUTION = "Information from the NHS website"
NHS_LICENSE_NOTES = (
    "OGL v3.0 — attribution required (Information from the NHS website). "
    "Refresh cached copy at least every 7 days per NHS terms."
)
WEEKLY_INTERVAL_MIN_DEFAULT = 7 * 24 * 60  # 10080
# Dedicated advisory lock for weekly crawler (distinct from device_disconnected).
WEEKLY_CRAWLER_ADVISORY_LOCK_KEY = 0x57365031  # 'W6P1'
CONTROLLED_ADAPTER_MODE = "PUBLIC_WEB_FETCH"
CONTROLLED_FETCH_METHOD = "html_page"
CONFIG_VERSION = "w6p01-governed-v1"
CANDIDATE_APPLICABILITY = "candidate_only_not_approved_knowledge"
# Existing know07 living-knowledge events reused for version lifecycle (no new engine).
SUPERSESSION_EVENT = "GUIDELINE_SUPERSESSION"
STALE_AFTER_FAILED_CHANGE_EVENT = "CORRECTION"
# Identity-scoped dedupe key used when the content key is already taken (content revert,
# or identical text under another source/URL identity).
VERSION_DEDUPE_NAMESPACE = "w6p01-ku-version-dedupe-v1"
# Provenance extraction_process prefix that marks section-level KUs (schema-free marker;
# KnowledgeUnit.canonicalization_version is constrained to "v1").
SECTION_EXTRACTION_PROCESS_PREFIX = "w3p01-conceptual-sections"
# Living knowledge: a crawled KU that the weekly crawler has not reconfirmed for this many
# days (page removed, URL dropped from the manifest, or fetch failing) stops serving.
WEEKLY_RECONFIRMATION_POLICY_DAYS = 35
WEEKLY_CRAWLER_ACCESS_ROUTE = "scheduled_weekly_crawler"
_NON_CURRENT_PUBLICATION_STATES = frozenset(
    {PublicationState.SUPERSEDED.value, PublicationState.WITHDRAWN.value}
)


class GovernedWeeklyRuntimeError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


@dataclass
class GovernedPersistResult:
    raw_evidence_ids: list[int] = field(default_factory=list)
    knowledge_unit_ids: list[int] = field(default_factory=list)
    provenance_ids: list[int] = field(default_factory=list)
    knowledge_memory_writes: int = 0
    new_knowledge_count: int = 0
    detail: str = ""
    superseded_knowledge_unit_ids: list[int] = field(default_factory=list)
    # Current versions retired because the page layout changed (document-level KU replaced
    # by section KUs, or a section that no longer exists on the page).
    retired_knowledge_unit_ids: list[int] = field(default_factory=list)
    stale_retired_knowledge_unit_ids: list[int] = field(default_factory=list)
    document_failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class NhsActivationResult:
    knowledge_source_id: int
    governed_source_profile_id: int
    source_version_id: Optional[int]
    created_source: bool
    created_profile: bool
    source_fetch_enabled: bool


def deterministic_weekly_window(
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    """Stable UTC week bucket (Mon 00:00 → +7d). Cadence remains 10080 minutes."""
    moment = now or utc_now()
    # Anchor: Monday 1970-01-05 00:00 UTC.
    anchor = datetime(1970, 1, 5, 0, 0, 0)
    delta_days = (moment.replace(hour=0, minute=0, second=0, microsecond=0) - anchor).days
    week_index = delta_days // 7
    start = anchor + timedelta(days=week_index * 7)
    end = start + timedelta(days=7)
    return start, end


def map_fetch_rights_to_retention(
    *,
    rights_terms_state: str,
    robots_access_state: str,
) -> tuple[str, str, str, str]:
    """Fail-closed retention decision.

    Full body retention is NOT authorized by structured governance for this Gate.
    OGL + ALLOWED permits hash/link minimal evidence only.
    """
    rights = (rights_terms_state or "").strip().upper()
    robots = (robots_access_state or "").strip().upper()
    if rights not in {"OGL", "APPROVED", "ACCEPTABLE", "PUBLIC_DOMAIN"}:
        raise GovernedWeeklyRuntimeError("RETENTION_RIGHTS_FAIL_CLOSED", rights or "empty")
    if robots not in {"ALLOWED", "ACCEPTABLE", "APPROVED"}:
        raise GovernedWeeklyRuntimeError("RETENTION_ROBOTS_FAIL_CLOSED", robots or "empty")
    # Persist RightsTermsState vocab (not adapter OGL token) on I5RawEvidence.
    return (
        RawRetentionMode.RAW_MINIMAL_EVIDENCE_ONLY.value,
        RawStorageMode.NONE.value,
        RightsTermsState.APPROVED.value,
        RobotsAccessState.ALLOWED.value,
    )


def try_acquire_weekly_advisory_lock(db: Any) -> bool:
    if db is None:
        return False
    bind = getattr(db, "get_bind", lambda: None)()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect != "postgresql":
        # Non-PG (unit) path: lock is a no-op success; logical_run_key still dedupes.
        return True
    row = db.execute(
        text("SELECT pg_try_advisory_lock(:key)"),
        {"key": WEEKLY_CRAWLER_ADVISORY_LOCK_KEY},
    )
    return bool(row.scalar())


def release_weekly_advisory_lock(db: Any) -> None:
    if db is None:
        return
    bind = getattr(db, "get_bind", lambda: None)()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_unlock(:key)"),
        {"key": WEEKLY_CRAWLER_ADVISORY_LOCK_KEY},
    )


def _parse_metadata(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_controlled_weekly_candidates(
    db: Any,
    models: Any,
    *,
    require_exact_nhs_sleep: bool = True,
) -> list[SourceCandidateDescriptor]:
    """Load ACTIVE/ELIGIBLE governed candidates from persisted source state."""
    if db is None or models is None:
        return []
    ks = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.slug == NHS_SOURCE_KEY)
        .one_or_none()
    )
    if ks is None:
        return []
    if not bool(ks.source_fetch_enabled):
        return []
    if not bool(ks.review_required):
        raise GovernedWeeklyRuntimeError("SOURCE_REVIEW_REQUIRED_MUST_BE_TRUE")
    if bool(ks.auto_approve_low_risk):
        raise GovernedWeeklyRuntimeError("SOURCE_AUTO_APPROVE_FORBIDDEN")
    if (ks.allowed_domain or "").strip().lower() != NHS_ALLOWED_DOMAIN:
        raise GovernedWeeklyRuntimeError("SOURCE_DOMAIN_MISMATCH", str(ks.allowed_domain))
    if (ks.fetch_method or "").strip() != CONTROLLED_FETCH_METHOD:
        raise GovernedWeeklyRuntimeError("SOURCE_FETCH_METHOD_MISMATCH", str(ks.fetch_method))
    if (ks.trust_level or "").strip().lower() != NHS_TRUST_LEVEL:
        raise GovernedWeeklyRuntimeError("SOURCE_TRUST_MISMATCH", str(ks.trust_level))

    meta = _parse_metadata(ks.metadata_json)
    target_url = (ks.source_url or "").strip() or str(meta.get("controlled_page_url") or "").strip()
    if require_exact_nhs_sleep and target_url != NHS_SLEEP_URL:
        raise GovernedWeeklyRuntimeError("SOURCE_URL_SCOPE_MISMATCH", target_url or "empty")

    gsp = (
        db.query(models.GovernedSourceProfile)
        .filter(models.GovernedSourceProfile.canonical_key == NHS_SOURCE_KEY)
        .one_or_none()
    )
    if gsp is None and ks.id is not None:
        gsp = (
            db.query(models.GovernedSourceProfile)
            .filter(models.GovernedSourceProfile.legacy_knowledge_source_id == ks.id)
            .one_or_none()
        )
    if gsp is None:
        return []
    if gsp.block_reason:
        raise GovernedWeeklyRuntimeError("SOURCE_BLOCKED", str(gsp.block_reason))
    if gsp.registry_state != "ACTIVE":
        return []
    if gsp.runtime_eligibility != "ELIGIBLE":
        return []
    if gsp.current_profile_version_id is None:
        return []
    if not gsp_persist.profile_is_fetch_eligible(gsp):
        return []

    version = gsp_persist.get_current_profile_version(db, profile_id=int(gsp.id))
    if version is None:
        return []
    # Rights/robots from version + KnowledgeSource robots flag.
    if ks.robots_allowed is not True:
        raise GovernedWeeklyRuntimeError("SOURCE_ROBOTS_NOT_ALLOWED")
    if (version.license_status or "") != LicenseStatus.EXPLICIT_GRANT.value:
        raise GovernedWeeklyRuntimeError("SOURCE_LICENSE_NOT_EXPLICIT", str(version.license_status))
    if (version.storage_permission or "") not in {
        PermissionDecision.ALLOW_EXPLICIT.value,
        PermissionDecision.DENY_EXPLICIT.value,
    }:
        # DENY_EXPLICIT body storage is expected for minimal evidence; ALLOW is also ok.
        raise GovernedWeeklyRuntimeError("SOURCE_STORAGE_PERMISSION_UNKNOWN", str(version.storage_permission))

    return [
        map_gsp_row_to_descriptor(
            source_profile_id=int(gsp.id),
            registry_state=str(gsp.registry_state),
            runtime_eligibility=str(gsp.runtime_eligibility),
            adapter_mode=CONTROLLED_ADAPTER_MODE,
            url=target_url,
            rights_terms_state="OGL",
            robots_access_state="ALLOWED",
            rate_limit_policy="DEFINED",
            allowed_domain=NHS_ALLOWED_DOMAIN,
            source_version_id=int(version.id),
            canonical_key=str(gsp.canonical_key),
        )
    ]


def _nhs_governance_evidence() -> dict[str, Any]:
    return {
        "publisher_authority_identity": "NHS UK",
        "source_class": SourceClass.KNOWLEDGE_DOCUMENT.value,
        "authority_evidence_tier": AuthorityTier.OFFICIAL_NATIONAL.value,
        "jurisdiction_scope": ClinicalJurisdictionScope.COUNTRY.value,
        "jurisdiction_country_code": "GB",
        "jurisdiction_subdivision_code": None,
        "jurisdiction_organization_id": None,
        "primary_language": "en",
        "specialty_domain": "lifestyle_sleep",
        "license_status": LicenseStatus.EXPLICIT_GRANT.value,
        "permitted_use_restriction": "ogl_v3_attribution_required",
        # Full body storage not authorized → deny raw body; hash/link metadata only.
        "storage_permission": PermissionDecision.DENY_EXPLICIT.value,
        "transformation_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "display_redistribution_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "automation_status": AutomationStatus.SCHEDULED_STAGE_ONLY.value,
        "verification_method": VerificationMethod.HUMAN_REVIEWED_DOCUMENT.value,
        "freshness_policy_days": 7,
        "freshness_status": FreshnessStatus.UNKNOWN_AGE.value,
        "fetch_policy": "controlled_public_web_fetch_nhs_sleep_only",
        "iran_first_applicable": False,
        "policy_version_reference": "gate3h-trusted_source_catalog_v1/nhs_uk_live_well",
        "configuration_version_reference": CONFIG_VERSION,
        "effective_at": datetime.now(timezone.utc),
    }


def activate_nhs_sleep_source(db: Any, models: Any) -> NhsActivationResult:
    """Idempotent KnowledgeSource + GSP activation for the single NHS sleep page."""
    if db is None or models is None:
        raise GovernedWeeklyRuntimeError("ACTIVATION_REQUIRES_DB")

    meta = {
        "topic_tags": ["prevention", "sleep"],
        "gate3h_group": "A",
        "batch1_precheck_robots": "allowed",
        "batch1_precheck_terms": "allowed_with_attribution",
        "controlled_page_key": NHS_PAGE_KEY,
        "controlled_page_url": NHS_SLEEP_URL,
        "allowed_url_patterns": [NHS_ALLOWED_URL_PATTERN],
        "attribution_required": NHS_ATTRIBUTION,
        "master_gate": "I5-W6-P01-REAL-GOVERNED-LEARNING-PIPELINE",
    }
    created_source = False
    ks = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.slug == NHS_SOURCE_KEY)
        .one_or_none()
    )
    if ks is None:
        created_source = True
        ks = models.KnowledgeSource(
            slug=NHS_SOURCE_KEY,
            name="NHS — Live Well",
            category="lifestyle",
            trust_level=NHS_TRUST_LEVEL,
            source_url=NHS_SLEEP_URL,
            locale="en",
            freshness_policy_days=7,
            ingestion_status="draft",
            license_notes=NHS_LICENSE_NOTES,
            metadata_json=json.dumps(meta, sort_keys=True),
            source_fetch_enabled=False,
            allowed_domain=NHS_ALLOWED_DOMAIN,
            allowed_url_patterns_json=json.dumps([NHS_ALLOWED_URL_PATTERN]),
            fetch_method=CONTROLLED_FETCH_METHOD,
            review_required=True,
            auto_approve_low_risk=False,
            fetch_interval_hours=168,
            robots_allowed=True,
            crawl_policy_json=json.dumps(
                {
                    "controlled_urls": [NHS_SLEEP_URL],
                    "max_urls_per_cycle": 1,
                    "forbid_sitewide_crawl": True,
                },
                sort_keys=True,
            ),
        )
        db.add(ks)
        db.flush()
    else:
        # Update mutable activation fields idempotently without broadening scope.
        ks.source_url = NHS_SLEEP_URL
        ks.allowed_domain = NHS_ALLOWED_DOMAIN
        ks.allowed_url_patterns_json = json.dumps([NHS_ALLOWED_URL_PATTERN])
        ks.fetch_method = CONTROLLED_FETCH_METHOD
        ks.review_required = True
        ks.auto_approve_low_risk = False
        ks.trust_level = NHS_TRUST_LEVEL
        ks.freshness_policy_days = 7
        ks.fetch_interval_hours = 168
        ks.robots_allowed = True
        ks.license_notes = NHS_LICENSE_NOTES
        ks.metadata_json = json.dumps(meta, sort_keys=True)
        ks.crawl_policy_json = json.dumps(
            {
                "controlled_urls": [NHS_SLEEP_URL],
                "max_urls_per_cycle": 1,
                "forbid_sitewide_crawl": True,
            },
            sort_keys=True,
        )
        db.flush()

    created_profile = False
    try:
        existing = gsp_persist.get_profile_by_canonical_key(db, NHS_SOURCE_KEY)
        profile = existing
    except gsp_persist.SourceProfilePersistenceError:
        created_profile = True
        profile = gsp_persist.create_or_get_profile(
            db,
            canonical_key=NHS_SOURCE_KEY,
            locator_kind="url",
            locator=NHS_SLEEP_URL,
            legacy_knowledge_source_id=int(ks.id),
        )

    version = gsp_persist.append_profile_version(
        db,
        profile_id=int(profile.id),
        governance_evidence=_nhs_governance_evidence(),
    )

    # Promote registry/runtime only after version exists; then enable fetch.
    profile.registry_state = "ACTIVE"
    profile.runtime_eligibility = "ELIGIBLE"
    profile.block_reason = None
    profile.operational_status = SourceOperationalStatus.ENABLED_IDLE.value
    profile.owner_reference = "Javad"
    profile.topic_coverage = "lifestyle/sleep"
    profile.last_reviewed_at = utc_now()
    profile.updated_at = utc_now()
    db.flush()

    if not gsp_persist.profile_is_fetch_eligible(profile):
        raise GovernedWeeklyRuntimeError("PROFILE_NOT_FETCH_ELIGIBLE")
    if profile.registry_state != "ACTIVE" or profile.runtime_eligibility != "ELIGIBLE":
        raise GovernedWeeklyRuntimeError("PROFILE_NOT_RUNTIME_ELIGIBLE")

    ks.source_fetch_enabled = True
    db.flush()

    return NhsActivationResult(
        knowledge_source_id=int(ks.id),
        governed_source_profile_id=int(profile.id),
        source_version_id=int(version.id) if version is not None else None,
        created_source=created_source,
        created_profile=created_profile,
        source_fetch_enabled=True,
    )


def deactivate_nhs_sleep_fetch(db: Any, models: Any) -> None:
    """Fail-closed rollback helper: disable fetch for the one NHS source."""
    if db is None or models is None:
        raise GovernedWeeklyRuntimeError("DEACTIVATION_REQUIRES_DB")
    ks = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.slug == NHS_SOURCE_KEY)
        .one_or_none()
    )
    if ks is not None:
        ks.source_fetch_enabled = False
        db.flush()
    gsp = (
        db.query(models.GovernedSourceProfile)
        .filter(models.GovernedSourceProfile.canonical_key == NHS_SOURCE_KEY)
        .one_or_none()
    )
    if gsp is not None:
        gsp.operational_status = SourceOperationalStatus.DISABLED.value
        gsp.runtime_eligibility = "NOT_ELIGIBLE"
        gsp.updated_at = utc_now()
        db.flush()


def _resolve_source_key(db: Any, models: Any, source_profile_id: int) -> str:
    gsp = db.query(models.GovernedSourceProfile).filter_by(id=int(source_profile_id)).one_or_none()
    if gsp is None:
        return ""
    return str(gsp.canonical_key or "")


def stable_document_identity(
    source_profile_id: int, canonical_url: str, section_key: str = ""
) -> str:
    """Content-independent document key. Fits source_document_id and canonical_unit_id.

    Without section_key this is the 81-C1 document identity. A non-empty section_key
    gives a per-section identity inside the same document (same 64-char column).
    """
    material = f"{int(source_profile_id)}|{(canonical_url or '').strip()}"
    section = (section_key or "").strip()
    if section:
        material = f"{material}|{section}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _backfill_source_document_id(row: Any, document_id: str) -> None:
    current = str(getattr(row, "source_document_id", None) or "").strip()
    if not current:
        row.source_document_id = document_id


def _prior_canonical_unit_ids(
    db: Any,
    models: Any,
    *,
    source_profile_id: int,
    canonical_url: str,
    section_level: bool = False,
) -> set[str]:
    marker = models.KnowledgeProvenance.extraction_process.like(
        f"{SECTION_EXTRACTION_PROCESS_PREFIX}%"
    )
    rows = (
        db.query(models.KnowledgeUnit.canonical_unit_id)
        .join(
            models.KnowledgeProvenance,
            models.KnowledgeProvenance.knowledge_unit_id == models.KnowledgeUnit.id,
        )
        .join(
            models.I5RawEvidence,
            models.I5RawEvidence.id == models.KnowledgeProvenance.raw_evidence_id,
        )
        .filter(models.I5RawEvidence.source_profile_id == int(source_profile_id))
        .filter(models.I5RawEvidence.canonical_url == canonical_url)
        .filter(
            marker
            if section_level
            else or_(models.KnowledgeProvenance.extraction_process.is_(None), ~marker)
        )
        .distinct()
        .all()
    )
    return {str(row[0]) for row in rows if row[0]}


def _resolve_canonical_unit_id(
    db: Any,
    models: Any,
    *,
    source_profile_id: int,
    canonical_url: str,
    section_key: str = "",
) -> str:
    if (section_key or "").strip():
        # Section identities are new; no legacy content-derived ids to adopt.
        return stable_document_identity(source_profile_id, canonical_url, section_key)
    prior = _prior_canonical_unit_ids(
        db,
        models,
        source_profile_id=source_profile_id,
        canonical_url=canonical_url,
    )
    if len(prior) > 1:
        raise GovernedWeeklyRuntimeError(
            "KU_DOCUMENT_IDENTITY_AMBIGUOUS",
            f"source_profile_id={int(source_profile_id)}",
        )
    if len(prior) == 1:
        return next(iter(prior))
    return stable_document_identity(source_profile_id, canonical_url)


def _version_number(version_id: Any) -> int:
    token = str(version_id or "").strip()
    if not (token.startswith("v") and token[1:].isdigit() and int(token[1:]) >= 1):
        raise GovernedWeeklyRuntimeError("KU_VERSION_ID_UNPARSEABLE", token)
    return int(token[1:])


def _current_knowledge_version(
    db: Any,
    models: Any,
    canonical_unit_id: str,
) -> tuple[Optional[Any], int, Optional[Any]]:
    """Return (current version, latest version number, latest row) for a logical identity.

    current is None when the identity is new, or when every version was retired by the
    lifecycle (e.g. a section that disappeared and came back): the caller then opens the
    next version. Ambiguous chains fail closed.
    """
    rows = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.canonical_unit_id == canonical_unit_id)
        .all()
    )
    if not rows:
        return None, 0, None
    numbered = sorted(((_version_number(r.immutable_version_id), r) for r in rows), key=lambda p: p[0])
    latest_number, latest = numbered[-1]
    if getattr(latest, "retraction_reason", None) or (
        str(getattr(latest, "publication_state", "") or "") == PublicationState.WITHDRAWN.value
    ):
        raise GovernedWeeklyRuntimeError("KU_CURRENT_VERSION_RETRACTED", canonical_unit_id)
    open_rows = [
        r
        for _, r in numbered
        if str(getattr(r, "publication_state", "") or "") not in _NON_CURRENT_PUBLICATION_STATES
    ]
    if len(open_rows) > 1:
        raise GovernedWeeklyRuntimeError("KU_MULTIPLE_CURRENT_VERSIONS", canonical_unit_id)
    if not open_rows:
        return None, latest_number, latest
    if open_rows[0] is not latest:
        raise GovernedWeeklyRuntimeError("KU_VERSION_CHAIN_BROKEN", canonical_unit_id)
    return latest, latest_number, latest


def _served_statement_changed(
    current: Any, statement: str, canonical_url: Optional[str] = None
) -> bool:
    """Material change = change in the served statement (not page chrome / page hash).

    Specialized eligibility may store a healed claim window instead of the raw claim,
    so the incoming claim is also compared after the same healing step.
    """
    stored = {"normalized_statement": getattr(current, "normalized_statement", None)}
    kind = sup_svc.detect_change_kind(stored, {"normalized_statement": statement})
    if kind == MemoryChangeKind.NO_MATERIAL_CHANGE:
        return False
    from backend.app.services.i5.governed_specialized_entity_eligibility import (
        select_clinical_claim_window,
    )

    healed = select_clinical_claim_window(statement, canonical_url=canonical_url)
    if not healed:
        return True
    kind = sup_svc.detect_change_kind(stored, {"normalized_statement": healed})
    return kind != MemoryChangeKind.NO_MATERIAL_CHANGE


def _version_dedupe_key(canonical_unit_id: str, version_id: str) -> str:
    material = f"{VERSION_DEDUPE_NAMESPACE}|{canonical_unit_id}|{version_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _row_dedupe_key(
    db: Any, models: Any, content_dedupe: str, canonical_unit_id: str, version_id: str
) -> str:
    """Content dedupe key when free (KNOW05 paths still see it); identity-scoped on collision.

    A collision means the same content already exists as another row (content revert to an
    older version, or identical text under another source/URL identity).
    """
    taken = (
        db.query(models.KnowledgeUnit.id)
        .filter(models.KnowledgeUnit.deduplication_key == content_dedupe)
        .first()
    )
    if taken is None:
        return content_dedupe
    return _version_dedupe_key(canonical_unit_id, version_id)


def _new_candidate_knowledge_unit(
    models: Any,
    payload: Mapping[str, Any],
    *,
    canonical_unit_id: str,
    version_id: str,
    statement: str,
    domain: str,
    topic: str,
    jurisdiction: str,
    dedupe: str,
    canon: str,
    supersedes_unit_id: Optional[int] = None,
) -> Any:
    assert_allowed_medical_safety_transition(
        MedicalSafetyState.UNKNOWN,
        MedicalSafetyState.PENDING_REVIEW,
    )
    medical = MedicalSafetyState.PENDING_REVIEW.value
    conflict = ConflictState.NONE.value
    high_risk = False
    if requires_human_review(domain, medical, conflict, high_risk):
        review_state = ReviewState.NOT_REVIEWED.value
    else:
        review_state = ReviewState.NOT_REVIEWED.value

    return models.KnowledgeUnit(
        canonical_unit_id=canonical_unit_id,
        immutable_version_id=version_id,
        supersedes_unit_id=supersedes_unit_id,
        domain=domain,
        topic_taxonomy=topic,
        disease_or_health_condition=str(payload.get("disease_or_health_condition") or "") or None,
        manifest_entity_id=str(payload.get("manifest_entity_id") or "") or None,
        manifest_track_id=str(payload.get("manifest_track_id") or "") or None,
        language=str(payload.get("language") or "en"),
        knowledge_type=KnowledgeType.OTHER.value,
        normalized_statement=statement,
        applicability=CANDIDATE_APPLICABILITY,
        population="general",
        jurisdiction=jurisdiction,
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=medical,
        conflict_state=conflict,
        freshness_state=FreshnessState.UNKNOWN.value,
        review_state=review_state,
        publication_state=PublicationState.DRAFT.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        provenance_complete=False,
        deduplication_key=dedupe,
        canonical_hash=canon,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )


def _apply_living_knowledge_event(db: Any, knowledge_unit_id: int, event: str) -> None:
    from backend.app.services.i5.know07.living_knowledge import apply_living_knowledge_event_to_ku

    apply_living_knowledge_event_to_ku(db, knowledge_unit_id=int(knowledge_unit_id), event=event)


@dataclass
class _DocumentContext:
    # Current versions whose source content changed in this document (for fail-closed retire).
    changed_current_ids: list[int] = field(default_factory=list)
    # (source_profile_id, canonical_url) -> section identities seen on the page this run.
    section_layouts: dict[tuple[int, str], set[str]] = field(default_factory=dict)
    # Serving KUs of this document with their URL/section, for semantic linking.
    semantic_targets: list[tuple[Any, str, str]] = field(default_factory=list)


def _handoff_payload(h: Any) -> Mapping[str, Any]:
    return getattr(h, "payload", None) or {}


def _handoff_kind(h: Any) -> Optional[str]:
    return getattr(h, "handoff_kind", None) or (h.get("handoff_kind") if isinstance(h, Mapping) else None)


def _group_handoffs_by_document(handoffs: Sequence[Any]) -> list[list[Any]]:
    """One group per (source_profile_id, canonical_url) — the unit of savepoint isolation."""
    groups: dict[tuple[str, str], list[Any]] = {}
    for h in handoffs:
        if _handoff_kind(h) not in {"RAW_EVIDENCE", "CANDIDATE", "PROVENANCE"}:
            continue
        payload = _handoff_payload(h)
        key = (
            str(payload.get("source_profile_id") or ""),
            str(payload.get("canonical_url") or "").strip(),
        )
        groups.setdefault(key, []).append(h)
    return list(groups.values())


def _persist_document(
    db: Any,
    models: Any,
    *,
    handoffs: Sequence[Any],
    run_id: int,
    result: GovernedPersistResult,
    ctx: _DocumentContext,
) -> None:
    """Persist RAW → KU version → provenance for one document (caller owns the savepoint)."""
    by_kind: dict[str, list[Any]] = {"RAW_EVIDENCE": [], "CANDIDATE": [], "PROVENANCE": []}
    for h in handoffs:
        by_kind[_handoff_kind(h)].append(h)

    raw_by_request_key: dict[str, Any] = {}
    ku_by_fingerprint: dict[str, Any] = {}

    for h in by_kind["RAW_EVIDENCE"]:
        payload = _handoff_payload(h)
        request_key = getattr(h, "request_key", "") or ""
        rights_token = str(payload.get("rights_terms_state") or "UNKNOWN")
        robots_token = str(payload.get("robots_access_state") or "UNKNOWN")
        retention_mode, storage_mode, rights_vocab, robots_vocab = map_fetch_rights_to_retention(
            rights_terms_state=rights_token,
            robots_access_state=robots_token,
        )
        content_hash = str(payload.get("content_sha256") or payload.get("content_hash") or "")
        if len(content_hash) != 64:
            raise GovernedWeeklyRuntimeError("RAW_CONTENT_HASH_INVALID", content_hash)
        canonical_url = str(payload.get("canonical_url") or "")
        source_profile_id = int(payload["source_profile_id"])
        document_id = stable_document_identity(source_profile_id, canonical_url)
        existing = (
            db.query(models.I5RawEvidence)
            .filter(
                models.I5RawEvidence.content_hash == content_hash,
                models.I5RawEvidence.source_profile_id == source_profile_id,
                models.I5RawEvidence.canonical_url == canonical_url,
            )
            .one_or_none()
        )
        if existing is not None:
            _backfill_source_document_id(existing, document_id)
            raw_by_request_key[request_key] = existing
            result.raw_evidence_ids.append(int(existing.id))
            continue
        raw = models.I5RawEvidence(
            source_profile_id=source_profile_id,
            source_document_id=document_id,
            source_version_id=str(payload.get("source_version_id") or "") or None,
            retrieval_run_id=int(run_id),
            retrieval_timestamp=utc_now(),
            canonical_url=canonical_url,
            content_hash=content_hash,
            byte_hash=str(payload.get("byte_hash") or content_hash),
            normalized_hash=str(payload.get("normalized_hash") or "") or None,
            hash_algorithm="SHA-256",
            mime_type=str(payload.get("mime_type") or "text/html"),
            language=str(payload.get("language") or "en"),
            jurisdiction=str(payload.get("jurisdiction") or "GB"),
            storage_mode=storage_mode,
            retention_mode=retention_mode,
            rights_terms_state=rights_vocab,
            robots_access_state=robots_vocab,
            redaction_state="NONE",
            prohibited_data_state="UNKNOWN",
            expiry_state="ACTIVE",
            created_by_run_id=int(run_id),
        )
        db.add(raw)
        db.flush()
        raw_by_request_key[request_key] = raw
        result.raw_evidence_ids.append(int(raw.id))

    for h in by_kind["CANDIDATE"]:
        payload = _handoff_payload(h)
        fingerprint = str(payload.get("candidate_fingerprint") or "")
        statement = str(payload.get("normalized_statement") or "").strip()
        if not statement:
            raise GovernedWeeklyRuntimeError("CANDIDATE_STATEMENT_EMPTY")
        ku_svc.validate_no_pii_markers(statement)
        domain = str(payload.get("domain") or "lifestyle")
        topic = str(payload.get("topic") or "sleep")
        jurisdiction = str(payload.get("jurisdiction") or "GB")
        dedupe = str(
            payload.get("dedupe_key")
            or ku_svc.build_deduplication_key(domain, topic, "general", jurisdiction, statement)
        )
        canon = str(
            payload.get("canonical_hash")
            or ku_svc.build_canonical_hash(
                statement, domain, KnowledgeType.OTHER.value, topic_taxonomy=topic
            )
        )

        # Logical identity is source+URL(+section), not content.
        source_profile_id = payload.get("source_profile_id")
        canonical_url = str(payload.get("canonical_url") or "").strip()
        if source_profile_id is None or not canonical_url:
            raise GovernedWeeklyRuntimeError("KU_DOCUMENT_IDENTITY_INCOMPLETE")
        section_key = str(payload.get("section_key") or "").strip()
        canonical_unit_id = _resolve_canonical_unit_id(
            db,
            models,
            source_profile_id=int(source_profile_id),
            canonical_url=canonical_url,
            section_key=section_key,
        )
        layout = (int(source_profile_id), canonical_url)
        if section_key:
            ctx.section_layouts.setdefault(layout, set()).add(canonical_unit_id)
        current, current_number, latest = _current_knowledge_version(db, models, canonical_unit_id)

        if current is None:
            # New identity (v1), or every earlier version was retired by the lifecycle (vN+1).
            # A different source/URL/section never reuses another identity's KU.
            version_id = f"v{current_number + 1}"
            ku = _new_candidate_knowledge_unit(
                models,
                payload,
                canonical_unit_id=canonical_unit_id,
                version_id=version_id,
                statement=statement,
                domain=domain,
                topic=topic,
                jurisdiction=jurisdiction,
                dedupe=_row_dedupe_key(db, models, dedupe, canonical_unit_id, version_id),
                canon=canon,
                supersedes_unit_id=int(latest.id) if latest is not None else None,
            )
            ku.last_reviewed_at = utc_now()
            db.add(ku)
            db.flush()
            if latest is not None:
                sup_svc.validate_supersession_link(ku, latest)
            ctx.semantic_targets.append((ku, canonical_url, section_key))
            ku_by_fingerprint[fingerprint] = ku
            result.knowledge_unit_ids.append(int(ku.id))
            result.new_knowledge_count += 1
            continue

        stale_current = str(current.freshness_state or "") == FreshnessState.STALE.value
        if not stale_current and not _served_statement_changed(current, statement, canonical_url):
            # NO_CHANGE: same served content for the same logical identity.
            current.last_reviewed_at = utc_now()
            ctx.semantic_targets.append((current, canonical_url, section_key))
            ku_by_fingerprint[fingerprint] = current
            result.knowledge_unit_ids.append(int(current.id))
            continue

        # CONTENT_CHANGE (or refresh of a version retired as stale): next immutable version.
        ctx.changed_current_ids.append(int(current.id))
        next_version = f"v{current_number + 1}"
        ku = _new_candidate_knowledge_unit(
            models,
            payload,
            canonical_unit_id=canonical_unit_id,
            version_id=next_version,
            statement=statement,
            domain=domain,
            topic=topic,
            jurisdiction=jurisdiction,
            dedupe=_row_dedupe_key(db, models, dedupe, canonical_unit_id, next_version),
            canon=canon,
            supersedes_unit_id=int(current.id),
        )
        ku.last_reviewed_at = utc_now()
        db.add(ku)
        db.flush()
        sup_svc.validate_supersession_link(ku, current)
        # Old version: SUPERSEDED + STALE + NOT_ELIGIBLE, and its KCE stop serving.
        _apply_living_knowledge_event(db, int(current.id), SUPERSESSION_EVENT)
        ctx.semantic_targets.append((ku, canonical_url, section_key))
        ku_by_fingerprint[fingerprint] = ku
        result.knowledge_unit_ids.append(int(ku.id))
        result.superseded_knowledge_unit_ids.append(int(current.id))

    # Pair provenance handoffs to KU + raw via payload keys (within this document only).
    for h in by_kind["PROVENANCE"]:
        payload = _handoff_payload(h)
        raw_key = str(payload.get("raw_evidence_request_key") or "")
        fingerprint = str(payload.get("candidate_fingerprint") or "")
        raw = raw_by_request_key.get(raw_key)
        ku = ku_by_fingerprint.get(fingerprint)
        if raw is None and len(raw_by_request_key) == 1:
            raw = next(iter(raw_by_request_key.values()))
        if ku is None and len(ku_by_fingerprint) == 1:
            ku = next(iter(ku_by_fingerprint.values()))
        if raw is None or ku is None:
            raise GovernedWeeklyRuntimeError("PROVENANCE_LINKAGE_INCOMPLETE")

        existing_prov = (
            db.query(models.KnowledgeProvenance)
            .filter(models.KnowledgeProvenance.knowledge_unit_id == int(ku.id))
            .one_or_none()
        )
        if existing_prov is not None:
            _backfill_source_document_id(
                existing_prov,
                stable_document_identity(int(raw.source_profile_id), str(raw.canonical_url or "")),
            )
            result.provenance_ids.append(int(existing_prov.id))
            incoming_source_profile_id = int(payload.get("source_profile_id") or raw.source_profile_id)
            source_key = _resolve_source_key(db, models, incoming_source_profile_id)
            apply_governed_finalize_and_lexical_index(
                db,
                ku,
                source_key=source_key,
                source_profile_id=incoming_source_profile_id,
                raw_evidence_id=int(raw.id),
                authoritative_provenance=existing_prov,
                incoming_source_profile_id=incoming_source_profile_id,
                canonical_url=str(raw.canonical_url or ""),
            )
            continue

        lineage = prov_svc.attach_hash_lineage(
            {},
            content_hash=str(raw.content_hash),
            byte_hash=str(raw.byte_hash) if raw.byte_hash else None,
            normalized_hash=str(raw.normalized_hash) if raw.normalized_hash else None,
        )
        prov_payload = {
            "knowledge_unit_id": int(ku.id),
            "source_profile_id": int(payload.get("source_profile_id") or raw.source_profile_id),
            "retrieval_method": str(payload.get("retrieval_method") or "PUBLIC_WEB_FETCH_HTTPS"),
            "raw_evidence_id": int(raw.id),
            **lineage,
        }
        prov_svc.require_provenance_complete(prov_payload)
        source_key = _resolve_source_key(db, models, int(prov_payload["source_profile_id"]))
        attr = manifest_attribution(source_key) if source_key else {
            "required_text": NHS_ATTRIBUTION,
            "license": "OGL-v3.0",
            "publisher": "NHS UK",
        }
        attribution = {
            "required_text": attr["required_text"],
            "license": attr["license"],
            "source_url": str(payload.get("canonical_url") or raw.canonical_url),
            "adapter_id": payload.get("adapter_id"),
            "adapter_version": payload.get("adapter_version"),
            "representation": payload.get("representation") or payload.get("content_format"),
            "section": payload.get("section_key") or None,
        }
        # Drop null provenance keys to keep attribution compact
        attribution = {k: v for k, v in attribution.items() if v is not None}
        prov = models.KnowledgeProvenance(
            knowledge_unit_id=int(ku.id),
            source_profile_id=int(prov_payload["source_profile_id"]),
            source_document_id=stable_document_identity(
                int(raw.source_profile_id), str(raw.canonical_url or "")
            ),
            source_version_id=str(payload.get("source_version_id") or "") or None,
            raw_evidence_id=int(raw.id),
            retrieval_method=str(prov_payload["retrieval_method"]),
            access_route="scheduled_weekly_crawler",
            content_hash=lineage.get("content_hash"),
            byte_hash=lineage.get("byte_hash"),
            normalized_hash=lineage.get("normalized_hash"),
            extraction_process=_provenance_extraction_process(payload),
            normalization_process=str(payload.get("normalization_process") or "w3p01-normalize"),
            attribution_data=json.dumps(attribution, sort_keys=True),
            citation_rendering_data=json.dumps(
                {"attribution": attr["required_text"], "url": raw.canonical_url},
                sort_keys=True,
            ),
        )
        db.add(prov)
        db.flush()
        result.provenance_ids.append(int(prov.id))

        ku.provenance_complete = True
        apply_governed_finalize_and_lexical_index(
            db,
            ku,
            source_key=source_key,
            source_profile_id=int(prov_payload["source_profile_id"]),
            raw_evidence_id=int(raw.id),
            authoritative_provenance=prov,
            incoming_source_profile_id=int(prov_payload["source_profile_id"]),
            canonical_url=str(raw.canonical_url or ""),
        )

        # Never write unapproved candidates into Knowledge Memory (I7/I8 boundary).
        mem_probe = {
            "supersession_state": "CURRENT",
            "runtime_eligibility": ku.runtime_eligibility,
        }
        mem_elig = mem_svc.evaluate_memory_eligibility(mem_probe)
        if mem_elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            result.knowledge_memory_writes = 0
        else:
            result.knowledge_memory_writes = 0

    # Concept / dimension links (KNOW02 taxonomy) for every serving KU of the document.
    from backend.app.services.i5.know02.concept_catalog import link_knowledge_unit_semantics

    for ku_row, ku_url, ku_section in ctx.semantic_targets:
        link_knowledge_unit_semantics(
            db,
            knowledge_unit_id=int(ku_row.id),
            canonical_url=ku_url,
            section_key=ku_section,
        )

    for (layout_source_id, layout_url), section_ids in ctx.section_layouts.items():
        result.retired_knowledge_unit_ids.extend(
            _retire_replaced_layout_versions(
                db,
                models,
                source_profile_id=layout_source_id,
                canonical_url=layout_url,
                keep_canonical_unit_ids=section_ids,
            )
        )


def retire_unconfirmed_weekly_knowledge(
    db: Any,
    models: Any,
    *,
    now: Optional[datetime] = None,
    policy_days: int = WEEKLY_RECONFIRMATION_POLICY_DAYS,
) -> list[int]:
    """Serving crawled KUs not reconfirmed within policy_days become STALE (fail closed).

    Reuses freshness_service for the decision and the know07 CORRECTION event for the
    transition (STALE, NOT_ELIGIBLE, KCE retracted). Only KUs written by the weekly
    crawler are in scope; other knowledge paths keep their own lifecycle.
    """
    from backend.app.services.i5.freshness_service import calculate_freshness_state

    moment = now or utc_now()
    rows = (
        db.query(models.KnowledgeUnit)
        .join(
            models.KnowledgeProvenance,
            models.KnowledgeProvenance.knowledge_unit_id == models.KnowledgeUnit.id,
        )
        .filter(models.KnowledgeProvenance.access_route == WEEKLY_CRAWLER_ACCESS_ROUTE)
        .filter(models.KnowledgeUnit.freshness_state == FreshnessState.CURRENT.value)
        .filter(~models.KnowledgeUnit.publication_state.in_(sorted(_NON_CURRENT_PUBLICATION_STATES)))
        .all()
    )
    retired: list[int] = []
    for ku in rows:
        anchor = ku.last_reviewed_at or ku.created_at
        state = calculate_freshness_state(now=moment, reviewed_at=anchor, policy_days=policy_days)
        if state == FreshnessState.CURRENT:
            continue
        _apply_living_knowledge_event(db, int(ku.id), STALE_AFTER_FAILED_CHANGE_EVENT)
        retired.append(int(ku.id))
    return retired


def record_lifecycle_counters(
    attempt: Any,
    persist_result: Optional[GovernedPersistResult],
    *,
    stale_unconfirmed_ids: Sequence[int] = (),
) -> None:
    """Write the run's real lifecycle outcome into the attempt ledger counters."""
    superseded = len(stale_unconfirmed_ids)
    if persist_result is not None:
        attempt.new_knowledge_count = int(persist_result.new_knowledge_count)
        attempt.updated_knowledge_count = len(persist_result.superseded_knowledge_unit_ids)
        attempt.rejected_knowledge_count = len(persist_result.document_failures)
        superseded += (
            len(persist_result.superseded_knowledge_unit_ids)
            + len(persist_result.retired_knowledge_unit_ids)
            + len(persist_result.stale_retired_knowledge_unit_ids)
        )
        # A document that failed closed is a warning on an otherwise completed run.
        attempt.warning_count = int(attempt.warning_count or 0) + len(persist_result.document_failures)
    attempt.superseded_knowledge_count = superseded


def _provenance_extraction_process(payload: Mapping[str, Any]) -> str:
    process = str(payload.get("extraction_process") or "w3p01-conceptual-1.0.0")
    if str(payload.get("section_key") or "").strip() and not process.startswith(
        SECTION_EXTRACTION_PROCESS_PREFIX
    ):
        return f"{SECTION_EXTRACTION_PROCESS_PREFIX}-1.0.0"
    return process


def _retire_replaced_layout_versions(
    db: Any,
    models: Any,
    *,
    source_profile_id: int,
    canonical_url: str,
    keep_canonical_unit_ids: set[str],
) -> list[int]:
    """The page is now section-based: retire the document-level KU and vanished sections.

    Uses the same know07 supersession event as a content change, so retired versions stop
    serving (SUPERSEDED, STALE, NOT_ELIGIBLE, KCE retracted). A retired section that comes
    back later opens a new version of its identity.
    """
    candidates = _prior_canonical_unit_ids(
        db, models, source_profile_id=source_profile_id, canonical_url=canonical_url
    ) | {stable_document_identity(source_profile_id, canonical_url)}
    candidates |= _prior_canonical_unit_ids(
        db,
        models,
        source_profile_id=source_profile_id,
        canonical_url=canonical_url,
        section_level=True,
    ) - set(keep_canonical_unit_ids)
    retired: list[int] = []
    for canonical_unit_id in sorted(candidates):
        open_rows = (
            db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.canonical_unit_id == canonical_unit_id)
            .filter(~models.KnowledgeUnit.publication_state.in_(sorted(_NON_CURRENT_PUBLICATION_STATES)))
            .all()
        )
        for row in open_rows:
            _apply_living_knowledge_event(db, int(row.id), SUPERSESSION_EVENT)
            retired.append(int(row.id))
    return retired


def _retire_stale_after_failed_change(db: Any, knowledge_unit_ids: Sequence[int]) -> list[int]:
    """Source changed but the new version could not be persisted: old evidence must not serve."""
    retired: list[int] = []
    for ku_id in knowledge_unit_ids:
        savepoint = db.begin_nested()
        try:
            _apply_living_knowledge_event(db, int(ku_id), STALE_AFTER_FAILED_CHANGE_EVENT)
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            # Cannot fail closed for this document → fail the whole run (caller rolls back).
            raise
        retired.append(int(ku_id))
    return retired


def execute_governed_persistence(
    db: Any,
    models: Any,
    *,
    handoffs: Sequence[Any],
    run_id: int,
    attempt_id: int,
) -> GovernedPersistResult:
    """Persist RAW → KU version → provenance per document, each inside its own savepoint.

    Same served content reuses the current version; changed content creates the next
    immutable version and supersedes the old one through existing know07 lifecycle events.
    A failing document rolls back alone (fail closed) and does not block other documents.
    """
    if db is None or models is None:
        raise GovernedWeeklyRuntimeError("PERSISTENCE_REQUIRES_DB")

    result = GovernedPersistResult()
    executed: list[Any] = []
    for doc_handoffs in _group_handoffs_by_document(handoffs):
        doc_result = GovernedPersistResult()
        ctx = _DocumentContext()
        savepoint = db.begin_nested()
        try:
            _persist_document(
                db,
                models,
                handoffs=doc_handoffs,
                run_id=run_id,
                result=doc_result,
                ctx=ctx,
            )
            # SCIS lexical indexing commits the session itself, which also ends this
            # savepoint; the document's work is then already durable.
            if savepoint.is_active:
                savepoint.commit()
        except Exception as exc:  # noqa: BLE001 — isolate and fail closed per document
            if not savepoint.is_active:
                # Failed after an inner commit: this document cannot be isolated any more.
                # Fail the whole run closed (caller rolls back the open transaction).
                raise
            savepoint.rollback()
            first = _handoff_payload(doc_handoffs[0])
            code = str(getattr(exc, "code", None) or type(exc).__name__)
            retired = _retire_stale_after_failed_change(db, ctx.changed_current_ids)
            result.stale_retired_knowledge_unit_ids.extend(retired)
            result.document_failures.append(
                {
                    "source_profile_id": first.get("source_profile_id"),
                    "canonical_url": str(first.get("canonical_url") or ""),
                    "code": code,
                    "stale_retired_knowledge_unit_ids": retired,
                }
            )
            print(
                "[I5 W6-P01] document persistence fail-closed "
                f"code={code} source_profile_id={first.get('source_profile_id')} "
                f"url={first.get('canonical_url')} stale_retired={retired} detail={str(exc)[:300]!r}"
            )
            continue
        result.raw_evidence_ids.extend(doc_result.raw_evidence_ids)
        result.knowledge_unit_ids.extend(doc_result.knowledge_unit_ids)
        result.provenance_ids.extend(doc_result.provenance_ids)
        result.new_knowledge_count += doc_result.new_knowledge_count
        result.superseded_knowledge_unit_ids.extend(doc_result.superseded_knowledge_unit_ids)
        result.retired_knowledge_unit_ids.extend(doc_result.retired_knowledge_unit_ids)
        executed.extend(doc_handoffs)

    result.detail = "governed_raw_ku_provenance_persisted"
    for h in executed:
        if hasattr(h, "execute"):
            h.execute = True
            if isinstance(getattr(h, "payload", None), dict):
                h.payload["execute"] = True
                h.payload["dry_run"] = False
                h.payload["attempt_id"] = attempt_id
    return result


def build_scheduled_logical_identity(
    *,
    candidates: Sequence[SourceCandidateDescriptor],
    now: Optional[datetime] = None,
) -> tuple[str, datetime, datetime, str]:
    start, end = deterministic_weekly_window(now)
    source_scope = json.dumps(
        [
            {
                "source_profile_id": c.source_profile_id,
                "adapter_mode": c.adapter_mode,
                # Exact endpoint identity — URL remediations must open a new logical run.
                "url": getattr(c, "url", None),
                "canonical_key": getattr(c, "canonical_key", None),
            }
            for c in candidates
        ],
        sort_keys=True,
    )
    import hashlib

    def _h(text_value: str) -> str:
        return hashlib.sha256(text_value.encode("utf-8")).hexdigest()

    source_scope_hash = _h(source_scope)
    domain_scope_hash = _h("{}")
    gap_scope_hash = _h("{}")
    config_hash = _h(CONFIG_VERSION)
    run_key = compute_logical_run_key(
        schedule_key=WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
        planned_window_start=start,
        planned_window_end=end,
        source_scope_hash=source_scope_hash,
        domain_scope_hash=domain_scope_hash,
        gap_scope_hash=gap_scope_hash,
        config_hash=config_hash,
    )
    return run_key, start, end, config_hash


def run_weekly_scheduled_job(
    db: Any = None,
    models: Any = None,
    *,
    candidates: Optional[Sequence[SourceCandidateDescriptor]] = None,
    persist_ledger: bool = True,
    live_http_get: Any = None,
    acquire_lock: bool = True,
    now: Optional[datetime] = None,
) -> OrchestrationOutcome:
    """Exact production scheduler-facing callable (APScheduler / CI / one-shot)."""
    owns_session = False
    session = db
    loaded_models = models
    if session is None:
        from backend.app.database import get_db
        import importlib

        session = next(get_db())
        owns_session = True
        loaded_models = importlib.import_module("backend.app.models")

    lock_held = False
    try:
        if acquire_lock:
            lock_held = try_acquire_weekly_advisory_lock(session)
            if not lock_held:
                return OrchestrationOutcome(
                    outcome="SKIPPED_ADVISORY_LOCK",
                    activation_enabled=os.environ.get(WEEKLY_ORCHESTRATOR_ENABLE_ENV, "")
                    .strip()
                    .lower()
                    in {"1", "true", "yes"},
                    scheduler_activation=os.environ.get(SOURCE_ACTIVATION_ENV, "")
                    .strip()
                    .lower()
                    in {"1", "true", "yes"},
                    production_write=False,
                    network_executed=False,
                    detail="weekly advisory lock held by another worker",
                )

        _ensure_concept_catalog_isolated(session)
        if candidates is not None:
            resolved = list(candidates)
        else:
            # Multisource when SEDI_I5_MULTISOURCE_ENABLED; else historical NHS-only path.
            from backend.app.services.i5.multisource_activation import resolve_weekly_candidates

            resolved = resolve_weekly_candidates(session, loaded_models)
        run_key, start, end, cfg_hash = build_scheduled_logical_identity(
            candidates=resolved, now=now
        )
        outcome = run_dormant_scheduled_tick(
            session,
            loaded_models,
            candidates=resolved,
            persist_ledger=persist_ledger,
            live_http_get=live_http_get,
            logical_run_key=run_key,
            planned_window_start=start,
            planned_window_end=end,
            config_version=CONFIG_VERSION,
            config_hash=cfg_hash,
        )
        if owns_session:
            session.commit()
        return outcome
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if lock_held:
            try:
                release_weekly_advisory_lock(session)
            except Exception:
                pass
        if owns_session:
            try:
                session.close()
            except Exception:
                pass


def _ensure_concept_catalog_isolated(db: Any) -> None:
    """Seed the governed concept catalog; a catalog problem never blocks the knowledge refresh."""
    if db is None:
        return
    savepoint = db.begin_nested()
    try:
        from backend.app.services.i5.know02.concept_catalog import ensure_concept_catalog

        counts = ensure_concept_catalog(db)
        savepoint.commit()
        print(f"[I5 W6-P01] concept catalog ensured {counts}")
    except Exception as exc:  # noqa: BLE001 — isolate; linking simply skips missing concepts
        if savepoint.is_active:
            savepoint.rollback()
        print(f"[I5 W6-P01] concept catalog skipped: {type(exc).__name__}: {str(exc)[:200]}")


def weekly_interval_minutes() -> int:
    raw = os.getenv("SEDI_I5_WEEKLY_ORCHESTRATOR_INTERVAL_MIN", str(WEEKLY_INTERVAL_MIN_DEFAULT))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = WEEKLY_INTERVAL_MIN_DEFAULT
    return max(60, min(14 * 24 * 60, value))


def weekly_first_run_delay_seconds() -> Optional[int]:
    """Optional one-shot first-fire delay after process start.

    Unset/invalid → None (APScheduler uses interval only).
    Bounded 30–600s so a canary scheduler tick can be proven without
    lowering the weekly cadence.
    """
    raw = os.getenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return max(30, min(600, value))


WEEKLY_SCHEDULER_TIMEZONE_NAME = "Asia/Tehran"
WEEKLY_CRON_DAY_OF_WEEK = "fri"
WEEKLY_CRON_HOUR = 3
WEEKLY_CRON_MINUTE = 30
WEEKLY_CRON_UTC_HOUR = 0
WEEKLY_CRON_UTC_MINUTE = 0


def weekly_scheduler_tz():
    """APScheduler timezone for the weekly job. Must match scheduler.py."""
    return pytz.timezone(WEEKLY_SCHEDULER_TIMEZONE_NAME)


def weekly_calendar_trigger_kwargs() -> dict[str, object]:
    """Fixed Friday 03:30 Asia/Tehran cron (= Friday 00:00 UTC). Restart-invariant."""
    return {
        "trigger": "cron",
        "day_of_week": WEEKLY_CRON_DAY_OF_WEEK,
        "hour": WEEKLY_CRON_HOUR,
        "minute": WEEKLY_CRON_MINUTE,
        "timezone": WEEKLY_SCHEDULER_TIMEZONE_NAME,
        "max_instances": 1,
        "coalesce": True,
    }


def next_weekly_calendar_fire(*, now: Optional[datetime] = None) -> datetime:
    """Next Friday 03:30 Asia/Tehran strictly after `now`. Independent of process start."""
    tz = weekly_scheduler_tz()
    if now is None:
        aware_now = datetime.now(tz)
    elif now.tzinfo is None:
        aware_now = tz.localize(now)
    else:
        aware_now = now.astimezone(tz)
    # Friday = 4 in Python weekday()
    days_ahead = (4 - aware_now.weekday()) % 7
    candidate = aware_now.replace(
        hour=WEEKLY_CRON_HOUR, minute=WEEKLY_CRON_MINUTE, second=0, microsecond=0
    ) + timedelta(days=days_ahead)
    if candidate <= aware_now:
        candidate = candidate + timedelta(days=7)
    utc = candidate.astimezone(pytz.UTC)
    if utc.weekday() != 4 or utc.hour != WEEKLY_CRON_UTC_HOUR or utc.minute != WEEKLY_CRON_UTC_MINUTE:
        raise RuntimeError(
            f"CALENDAR_UTC_MISMATCH tehran={candidate.isoformat()} utc={utc.isoformat()}"
        )
    return candidate


def weekly_first_run_at(delay_sec: int, *, now: Optional[datetime] = None) -> datetime:
    """Return a timezone-aware first-fire instant in the weekly scheduler TZ.

    Naive datetimes are localized as Asia/Tehran, never treated as UTC.
    A UTC-container datetime.now() passed to APScheduler(Asia/Tehran) as naive
    next_run_time is ~3.5h in the past and is misfire-skipped.
    """
    tz = weekly_scheduler_tz()
    if now is None:
        aware_now = datetime.now(tz)
    elif now.tzinfo is None:
        aware_now = tz.localize(now)
    else:
        aware_now = now.astimezone(tz)
    return aware_now + timedelta(seconds=int(delay_sec))


__all__ = [
    "PACKAGE_ID",
    "NHS_SOURCE_KEY",
    "NHS_SLEEP_URL",
    "WEEKLY_INTERVAL_MIN_DEFAULT",
    "WEEKLY_CRAWLER_ADVISORY_LOCK_KEY",
    "WEEKLY_ORCHESTRATOR_JOB_ID",
    "GovernedWeeklyRuntimeError",
    "GovernedPersistResult",
    "NhsActivationResult",
    "deterministic_weekly_window",
    "map_fetch_rights_to_retention",
    "try_acquire_weekly_advisory_lock",
    "release_weekly_advisory_lock",
    "load_controlled_weekly_candidates",
    "activate_nhs_sleep_source",
    "deactivate_nhs_sleep_fetch",
    "execute_governed_persistence",
    "build_scheduled_logical_identity",
    "run_weekly_scheduled_job",
    "weekly_interval_minutes",
    "weekly_first_run_delay_seconds",
    "WEEKLY_SCHEDULER_TIMEZONE_NAME",
    "WEEKLY_CRON_DAY_OF_WEEK",
    "WEEKLY_CRON_HOUR",
    "WEEKLY_CRON_MINUTE",
    "weekly_scheduler_tz",
    "weekly_calendar_trigger_kwargs",
    "next_weekly_calendar_fire",
    "weekly_first_run_at",
]
