"""Multi-source weekly activation allowlist (exact endpoints only)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

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
from backend.app.services.i5.governed_weekly_runtime import (
    CONTROLLED_ADAPTER_MODE,
    CONTROLLED_FETCH_METHOD,
    CONFIG_VERSION,
    GovernedWeeklyRuntimeError,
    utc_now,
)
from backend.app.services.i5.source_discovery import (
    SourceCandidateDescriptor,
    map_gsp_row_to_descriptor,
)

PACKAGE_ID = "I5-MULTISOURCE-ACTIVATION-V1"
ALLOWLIST_RELATIVE = Path("backend/config/i5/multisource_activation_allowlist_v1.yaml")
MULTISOURCE_ENV = "SEDI_I5_MULTISOURCE_ENABLED"


@dataclass
class MultisourceActivationResult:
    activated_source_keys: list[str]
    created_sources: int
    created_profiles: int
    fetch_enabled_count: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def load_multisource_allowlist() -> dict[str, Any]:
    path = _repo_root() / ALLOWLIST_RELATIVE
    if not path.is_file():
        raise GovernedWeeklyRuntimeError("MULTISOURCE_ALLOWLIST_MISSING", str(path))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("sources"):
        raise GovernedWeeklyRuntimeError("MULTISOURCE_ALLOWLIST_INVALID")
    return data


def multisource_enabled() -> bool:
    return os.environ.get(MULTISOURCE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _activation_yes(value: Any) -> bool:
    """YAML may coerce YES/Yes to bool True — accept both."""
    if value is True:
        return True
    return str(value or "").strip().upper() in {"YES", "TRUE", "1"}


def active_allowlist_rows() -> list[dict[str, Any]]:
    rows = []
    for row in load_multisource_allowlist().get("sources") or []:
        if not _activation_yes(row.get("activation")):
            continue
        if not row.get("exact_url") or not row.get("source_key"):
            raise GovernedWeeklyRuntimeError("ALLOWLIST_ROW_INCOMPLETE", str(row.get("source_key")))
        rows.append(row)
    if len(rows) < 2:
        raise GovernedWeeklyRuntimeError("ALLOWLIST_TOO_SMALL", str(len(rows)))
    families = {str(r.get("publisher_family") or r.get("allowed_domain")) for r in rows}
    if len(families) < 4:
        raise GovernedWeeklyRuntimeError("PUBLISHER_DIVERSITY_BELOW_FLOOR", str(sorted(families)))
    return rows


def _governance_evidence(row: dict[str, Any]) -> dict[str, Any]:
    rights = str(row.get("rights_terms_state") or "UNKNOWN").upper()
    if rights not in {"OGL", "PUBLIC_DOMAIN", "APPROVED", "ACCEPTABLE"}:
        raise GovernedWeeklyRuntimeError("ALLOWLIST_RIGHTS_FAIL_CLOSED", rights)
    return {
        "publisher_authority_identity": str(row.get("publisher") or ""),
        "source_class": SourceClass.KNOWLEDGE_DOCUMENT.value,
        "authority_evidence_tier": AuthorityTier.OFFICIAL_NATIONAL.value,
        "jurisdiction_scope": ClinicalJurisdictionScope.COUNTRY.value,
        "jurisdiction_country_code": "US" if "nih" in str(row.get("allowed_domain")) or "cdc" in str(row.get("allowed_domain")) or "medlineplus" in str(row.get("allowed_domain")) else "GB",
        "jurisdiction_subdivision_code": None,
        "jurisdiction_organization_id": None,
        "primary_language": "en",
        "specialty_domain": ",".join(row.get("knowledge_domains") or []) or "general",
        "license_status": LicenseStatus.EXPLICIT_GRANT.value,
        "permitted_use_restriction": str(row.get("license_notes") or "attribution_required")[:240],
        "storage_permission": PermissionDecision.DENY_EXPLICIT.value,
        "transformation_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "display_redistribution_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "automation_status": AutomationStatus.SCHEDULED_STAGE_ONLY.value,
        "verification_method": VerificationMethod.HUMAN_REVIEWED_DOCUMENT.value,
        "freshness_policy_days": 7,
        "freshness_status": FreshnessStatus.UNKNOWN_AGE.value,
        "fetch_policy": f"controlled_public_web_fetch:{row['source_key']}",
        "iran_first_applicable": False,
        "policy_version_reference": f"multisource_activation_allowlist_v1/{row['source_key']}",
        "configuration_version_reference": CONFIG_VERSION,
        "effective_at": utc_now(),
    }


def activate_multisource_allowlist(db: Any, models: Any) -> MultisourceActivationResult:
    """Idempotently activate every ACTIVATION=YES allowlist source (exact URLs only)."""
    if db is None or models is None:
        raise GovernedWeeklyRuntimeError("ACTIVATION_REQUIRES_DB")
    rows = active_allowlist_rows()
    created_sources = 0
    created_profiles = 0
    activated: list[str] = []

    for row in rows:
        key = str(row["source_key"])
        primary_url = str(row["exact_url"]).strip()
        extra = [str(u).strip() for u in (row.get("additional_urls") or []) if str(u).strip()]
        controlled_urls = [primary_url] + [u for u in extra if u != primary_url]
        patterns = list(row.get("allowed_url_patterns") or [])
        domain = str(row.get("allowed_domain") or "").strip().lower()
        meta = {
            "gate": PACKAGE_ID,
            "controlled_page_url": primary_url,
            "controlled_urls": controlled_urls,
            "entity_coverage": row.get("entity_coverage") or [],
            "knowledge_domains": row.get("knowledge_domains") or [],
            "rights_terms_state": row.get("rights_terms_state"),
            "robots_access_state": row.get("robots_access_state"),
            "attribution_required": True,
        }
        ks = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.slug == key).one_or_none()
        if ks is None:
            created_sources += 1
            ks = models.KnowledgeSource(
                slug=key,
                name=str(row.get("publisher") or key),
                category="lifestyle",
                trust_level="official",
                source_url=primary_url,
                locale="en",
                freshness_policy_days=7,
                ingestion_status="draft",
                license_notes=str(row.get("license_notes") or "")[:2000],
                metadata_json=json.dumps(meta, sort_keys=True),
                source_fetch_enabled=False,
                allowed_domain=domain,
                allowed_url_patterns_json=json.dumps(patterns),
                fetch_method=CONTROLLED_FETCH_METHOD,
                review_required=True,
                auto_approve_low_risk=False,
                fetch_interval_hours=168,
                robots_allowed=True,
                crawl_policy_json=json.dumps(
                    {
                        "controlled_urls": controlled_urls,
                        "max_urls_per_cycle": len(controlled_urls),
                        "forbid_sitewide_crawl": True,
                    },
                    sort_keys=True,
                ),
            )
            db.add(ks)
            db.flush()
        else:
            ks.source_url = primary_url
            ks.allowed_domain = domain
            ks.allowed_url_patterns_json = json.dumps(patterns)
            ks.fetch_method = CONTROLLED_FETCH_METHOD
            ks.review_required = True
            ks.auto_approve_low_risk = False
            ks.trust_level = "official"
            ks.freshness_policy_days = 7
            ks.fetch_interval_hours = 168
            ks.robots_allowed = True
            ks.license_notes = str(row.get("license_notes") or "")[:2000]
            ks.metadata_json = json.dumps(meta, sort_keys=True)
            ks.crawl_policy_json = json.dumps(
                {
                    "controlled_urls": controlled_urls,
                    "max_urls_per_cycle": len(controlled_urls),
                    "forbid_sitewide_crawl": True,
                },
                sort_keys=True,
            )
            db.flush()

        try:
            profile = gsp_persist.get_profile_by_canonical_key(db, key)
        except gsp_persist.SourceProfilePersistenceError:
            created_profiles += 1
            profile = gsp_persist.create_or_get_profile(
                db,
                canonical_key=key,
                locator_kind="url",
                locator=primary_url,
                legacy_knowledge_source_id=int(ks.id),
            )

        version = gsp_persist.append_profile_version(
            db,
            profile_id=int(profile.id),
            governance_evidence=_governance_evidence(row),
        )
        profile.registry_state = "ACTIVE"
        profile.runtime_eligibility = "ELIGIBLE"
        profile.block_reason = None
        profile.operational_status = SourceOperationalStatus.ENABLED_IDLE.value
        profile.owner_reference = "Javad"
        profile.topic_coverage = ",".join(row.get("knowledge_domains") or [])[:240]
        profile.last_reviewed_at = utc_now()
        profile.updated_at = utc_now()
        db.flush()
        if not gsp_persist.profile_is_fetch_eligible(profile):
            raise GovernedWeeklyRuntimeError("PROFILE_NOT_FETCH_ELIGIBLE", key)
        ks.source_fetch_enabled = True
        db.flush()
        activated.append(key)
        _ = version

    # Fail closed: disable fetch for non-allowlist enabled sources.
    allow = set(activated)
    enabled = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.source_fetch_enabled.is_(True))
        .all()
    )
    for ks in enabled:
        if ks.slug not in allow:
            ks.source_fetch_enabled = False
    db.flush()

    return MultisourceActivationResult(
        activated_source_keys=activated,
        created_sources=created_sources,
        created_profiles=created_profiles,
        fetch_enabled_count=len(activated),
    )


def load_multisource_weekly_candidates(db: Any, models: Any) -> list[SourceCandidateDescriptor]:
    """Load all ACTIVE/ELIGIBLE allowlisted fetch-enabled sources (multi URL via crawl policy)."""
    if db is None or models is None:
        return []
    allow_rows = {str(r["source_key"]): r for r in active_allowlist_rows()}
    descriptors: list[SourceCandidateDescriptor] = []
    for key, row in sorted(allow_rows.items()):
        ks = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.slug == key).one_or_none()
        if ks is None or not bool(ks.source_fetch_enabled):
            continue
        if not bool(ks.review_required) or bool(ks.auto_approve_low_risk):
            raise GovernedWeeklyRuntimeError("SOURCE_REVIEW_GATE_FAILED", key)
        if (ks.allowed_domain or "").strip().lower() != str(row.get("allowed_domain")).strip().lower():
            raise GovernedWeeklyRuntimeError("SOURCE_DOMAIN_MISMATCH", key)
        if ks.robots_allowed is not True:
            raise GovernedWeeklyRuntimeError("SOURCE_ROBOTS_NOT_ALLOWED", key)
        gsp = (
            db.query(models.GovernedSourceProfile)
            .filter(models.GovernedSourceProfile.canonical_key == key)
            .one_or_none()
        )
        if gsp is None:
            continue
        if gsp.block_reason or gsp.registry_state != "ACTIVE" or gsp.runtime_eligibility != "ELIGIBLE":
            continue
        if gsp.current_profile_version_id is None or not gsp_persist.profile_is_fetch_eligible(gsp):
            continue
        version = gsp_persist.get_current_profile_version(db, profile_id=int(gsp.id))
        if version is None:
            continue
        if (version.license_status or "") != LicenseStatus.EXPLICIT_GRANT.value:
            raise GovernedWeeklyRuntimeError("SOURCE_LICENSE_NOT_EXPLICIT", key)

        policy = {}
        try:
            policy = json.loads(ks.crawl_policy_json or "{}")
        except (TypeError, ValueError):
            policy = {}
        urls = list(policy.get("controlled_urls") or [])
        if not urls:
            urls = [str(row["exact_url"])]
        rights = str(row.get("rights_terms_state") or "UNKNOWN")
        robots = str(row.get("robots_access_state") or "UNKNOWN")
        for url in urls:
            descriptors.append(
                map_gsp_row_to_descriptor(
                    source_profile_id=int(gsp.id),
                    registry_state=str(gsp.registry_state),
                    runtime_eligibility=str(gsp.runtime_eligibility),
                    adapter_mode=CONTROLLED_ADAPTER_MODE,
                    url=str(url),
                    rights_terms_state=rights,
                    robots_access_state=robots,
                    rate_limit_policy="DEFINED",
                    allowed_domain=str(row.get("allowed_domain")),
                    source_version_id=int(version.id),
                    canonical_key=key,
                )
            )
    return descriptors


def resolve_weekly_candidates(db: Any, models: Any) -> list[SourceCandidateDescriptor]:
    """Production resolver: multisource when enabled, else historical NHS-only loader."""
    from backend.app.services.i5 import governed_weekly_runtime as runtime

    if multisource_enabled():
        return load_multisource_weekly_candidates(db, models)
    return runtime.load_controlled_weekly_candidates(db, models, require_exact_nhs_sleep=True)


__all__ = [
    "PACKAGE_ID",
    "MULTISOURCE_ENV",
    "MultisourceActivationResult",
    "load_multisource_allowlist",
    "multisource_enabled",
    "active_allowlist_rows",
    "activate_multisource_allowlist",
    "load_multisource_weekly_candidates",
    "resolve_weekly_candidates",
]
