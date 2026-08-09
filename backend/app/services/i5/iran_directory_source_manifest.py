"""Governed source policy for Iran directory acquisition."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

IRIMC_SOURCE = "irimc_member_search"
SBMU_FED_HOSPITAL_SOURCE = "fed_sbmu_affiliated_hospitals"
MAX_CONCURRENT_SEARCHES = 1
# IRIMC publishes max 10 searches / 10 minutes → >=60s between searches.
MIN_SEARCH_INTERVAL_SECONDS = 60
MAX_RESULTS_PER_SEARCH = 100
ROBOTS_DISALLOW_PREFIXES = ("/admin/",)

SOURCE_MANIFEST: dict[str, dict[str, Any]] = {
    IRIMC_SOURCE: {
        "SOURCE_KEY": IRIMC_SOURCE,
        "PUBLISHER": "Iranian Medical Council (IRIMC)",
        "OFFICIAL_DOMAIN": "irimc.org",
        "SOURCE_URL": "https://membersearch.irimc.org/",
        "entity_family": "DOCTOR",
        "ENTITY_FAMILIES": ("DOCTOR",),
        "AUTHORITY_CLASS": "TIER1_OFFICIAL_STATUTORY_REGISTRY",
        "ACCESS_METHOD": "public_html_form_post",
        "PUBLIC_ACCESS": True,
        "AUTHENTICATION_REQUIRED": False,
        "CAPTCHA_PRESENT": False,
        "PAYWALL_PRESENT": False,
        "TERMS_URL": "https://irimc.org/",
        "TERMS_CHECK_RESULT": "PUBLIC_FACTUAL_MEMBER_DIRECTORY_NO_AUTOMATION_BAN_FOUND_IN_LANDING",
        "ROBOTS_URL": "https://membersearch.irimc.org/robots.txt",
        "ROBOTS_CHECK_RESULT": "User-agent:* Disallow:/admin/ only; searchresult allowed",
        "AUTOMATION_PROHIBITION_FOUND": False,
        "RIGHTS_BASIS": "Official public professional registry facts; attribution via source_system_label",
        "FACTS_ONLY_EXTRACTION": True,
        "ATTRIBUTION_REQUIRED": True,
        "RATE_LIMIT_PUBLISHED": "max 10 searches / 10 minutes; max 100 results / search",
        "CONSERVATIVE_REQUEST_POLICY": "single concurrency; sleep>=60s between searches; cookie+token session",
        "STABLE_EXTERNAL_RECORD_ID_AVAILABLE": True,
        "PAGINATION_METHOD": "single_page_capped_100",
        "FIELDS_AVAILABLE": (
            "first_name",
            "last_name",
            "mc_code",
            "degree_field",
            "office_city",
            "membership_type",
            "profile_uuid",
        ),
        "PROVIDER_DATA_TYPE": "professional_person_directory",
        "PERSONAL_DATA_RISK": "public_professional_identity",
        "PATIENT_DATA_PRESENT": False,
        "ALLOWED_FOR_SAMPLE_FETCH": True,
        "ALLOWED_FOR_V1_POPULATION": True,
        "base_url": "https://membersearch.irimc.org",
        "allowed_paths": ("/", "/searchresult", "/member/profile"),
        "REASON": "Tier-1 official statutory member search; robots allow; rate limit honored",
        "notes": "Members are people, never laboratory/hospital facilities.",
    },
    SBMU_FED_HOSPITAL_SOURCE: {
        "SOURCE_KEY": SBMU_FED_HOSPITAL_SOURCE,
        "PUBLISHER": "Shahid Beheshti University of Medical Sciences (SBMU)",
        "OFFICIAL_DOMAIN": "sbmu.ac.ir",
        "SOURCE_URL": (
            "https://sbmu.ac.ir/Virtual_Tour/"
            "%D8%A8%DB%8C%D9%85%D8%A7%D8%B1%D8%B3%D8%AA%D8%A7%D9%86"
        ),
        "entity_family": "HOSPITAL",
        "ENTITY_FAMILIES": ("HOSPITAL", "MEDICAL_CENTER"),
        "AUTHORITY_CLASS": "TIER1B_OFFICIAL_MEDICAL_UNIVERSITY_FEDERATED_PROVIDER_WEB",
        "ACCESS_METHOD": "public_web_fact_distillation",
        "PUBLIC_ACCESS": True,
        "AUTHENTICATION_REQUIRED": False,
        "CAPTCHA_PRESENT": False,
        "PAYWALL_PRESENT": False,
        "TERMS_URL": "https://www.sbmu.ac.ir/",
        "TERMS_CHECK_RESULT": "NO_EXPRESS_AUTOMATION_BAN_FOUND_ON_PUBLIC_LANDING; ABSENCE_NOT_PERMISSION",
        "ROBOTS_URL": "https://www.sbmu.ac.ir/robots.txt",
        "ROBOTS_CHECK_RESULT": "User-agent:* Allow:/",
        "AUTOMATION_PROHIBITION_FOUND": False,
        "RIGHTS_BASIS": (
            "Official university public facility affiliation facts; "
            "INTERNAL_FACT_EVIDENCE_DISTILLATION + attribution via source_system_label; "
            "no clinical authority"
        ),
        "FACTS_ONLY_EXTRACTION": True,
        "CONTENT_USE_MODE": "FACTS_PLUS_REWRITTEN_STRUCTURED_KNOWLEDGE_PLUS_PROVENANCE",
        "ATTRIBUTION_REQUIRED": True,
        "RATE_LIMIT_PUBLISHED": "none published; conservative single GET per acquisition",
        "CONSERVATIVE_REQUEST_POLICY": "single concurrency; official-domain host lock",
        "STABLE_EXTERNAL_RECORD_ID_AVAILABLE": False,
        "PAGINATION_METHOD": "single_page_affiliated_list",
        "FIELDS_AVAILABLE": (
            "name",
            "facility_type",
            "city",
            "province",
            "source_page_url",
        ),
        "PROVIDER_DATA_TYPE": "official_affiliated_facility_directory_facts",
        "PERSONAL_DATA_RISK": "none_facility_names_only",
        "PATIENT_DATA_PRESENT": False,
        "ALLOWED_FOR_SAMPLE_FETCH": True,
        "ALLOWED_FOR_V1_POPULATION": True,
        "base_url": "https://sbmu.ac.ir",
        "allowed_paths": ("/", "/Virtual_Tour", "/bimarestan"),
        "COVERAGE_CLASS": "OFFICIAL_FEDERATED_SEED",
        "NATIONWIDE_COMPLETE": False,
        "REASON": (
            "Gate-02 federated official provider-web member: SBMU Virtual Tour lists "
            "affiliated hospitals/medical centers; robots Allow:/; public access; "
            "facts-only distillation; coverage is university-affiliated seed not nationwide."
        ),
        "notes": "CAP25 GOVERNED_FEDERATED_OFFICIAL_PROVIDER_WEB_SOURCE; IR→KU forbidden.",
        "CHECKED_AT_UTC": "2026-08-09T07:30:00Z",
    },
    "iran_hospital_official_pending": {
        "SOURCE_KEY": "iran_hospital_official_pending",
        "entity_family": "HOSPITAL",
        "ENTITY_FAMILIES": ("HOSPITAL", "MEDICAL_CENTER"),
        "AUTHORITY_CLASS": "SUPERSEDED_BY_FEDERATION_MEMBER",
        "base_url": None,
        "allowed_paths": (),
        "ALLOWED_FOR_SAMPLE_FETCH": False,
        "ALLOWED_FOR_V1_POPULATION": False,
        "AUTOMATION_PROHIBITION_FOUND": True,
        "REASON": (
            "Central national registry still unresolved (behdasht CAPTCHA; AVAB auth; "
            "TUMS/SUMS 403; aggregators Tier-3). CAP25 V1 population uses "
            f"{SBMU_FED_HOSPITAL_SOURCE} federated member instead."
        ),
        "notes": "Placeholder retained for audit; not a population source.",
        "CHECKED_AT_UTC": "2026-08-09T07:30:00Z",
    },
    "iran_laboratory_official_pending": {
        "SOURCE_KEY": "iran_laboratory_official_pending",
        "entity_family": "LABORATORY",
        "ENTITY_FAMILIES": ("LABORATORY",),
        "AUTHORITY_CLASS": "UNRESOLVED",
        "base_url": None,
        "allowed_paths": (),
        "ALLOWED_FOR_SAMPLE_FETCH": False,
        "ALLOWED_FOR_V1_POPULATION": False,
        "AUTOMATION_PROHIBITION_FOUND": False,
        "REASON": (
            "Gate-02 federated official provider-web authorized, but no admissible "
            "clinical laboratory FACILITY member verified: IRIMC=persons; ISIRI=calibration; "
            "SBMU Virtual Tour hospital list contains zero clinical laboratories; "
            "individual lab-owned sites SSL/timeout from acquisition path; "
            "commercial portals remain Tier-3 discovery-only."
        ),
        "notes": "CAP24 BLOCKED_SOURCE_AUTHORITY; federation mode ON but zero admissible lab members.",
        "CHECKED_AT_UTC": "2026-08-09T07:30:00Z",
    },
}


class SourceNotAuthorizedError(ValueError):
    """Raised when a source is unknown or not approved for population."""


def get_authorized_source(source_system_label: str) -> dict[str, Any]:
    source = SOURCE_MANIFEST.get(str(source_system_label or "").strip())
    if source is None or not source["ALLOWED_FOR_V1_POPULATION"]:
        raise SourceNotAuthorizedError(f"SOURCE_NOT_AUTHORIZED:{source_system_label}")
    return source


def robots_path_allowed(source_system_label: str, path: str) -> bool:
    """Classify a path using the approved source scope, failing closed."""
    try:
        source = get_authorized_source(source_system_label)
    except SourceNotAuthorizedError:
        return False
    parsed = urlparse(path)
    candidate = parsed.path or "/"
    if any(candidate == deny.rstrip("/") or candidate.startswith(deny) for deny in ROBOTS_DISALLOW_PREFIXES):
        return False
    return any(
        candidate == allowed or (allowed != "/" and candidate.startswith(f"{allowed}/"))
        for allowed in source["allowed_paths"]
    )
