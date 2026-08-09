"""Governed source policy for Iran directory acquisition."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

IRIMC_SOURCE = "irimc_member_search"
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
    "iran_hospital_official_pending": {
        "SOURCE_KEY": "iran_hospital_official_pending",
        "entity_family": "HOSPITAL",
        "ENTITY_FAMILIES": ("HOSPITAL", "MEDICAL_CENTER"),
        "AUTHORITY_CLASS": "UNRESOLVED",
        "base_url": None,
        "allowed_paths": (),
        "ALLOWED_FOR_SAMPLE_FETCH": False,
        "ALLOWED_FOR_V1_POPULATION": False,
        "AUTOMATION_PROHIBITION_FOUND": True,
        "REASON": (
            "Broader Gate discovery still unresolved for V1 population: "
            "behdasht.gov.ir presents CAPTCHA/anti-bot gate; "
            "AVAB (avab.behdasht.gov.ir) requires authenticated login (not public directory); "
            "data.gov.ir/behdasht lacks free national structured hospital facility feed; "
            "TUMS/SUMS robots or portals HTTP 403; "
            "SBMU robots Allow:/ but no admissible structured public hospital registry endpoint proven; "
            "paid commercial datasets and aggregators remain Tier-3 discovery-only."
        ),
        "notes": "CAP25 BLOCKED_SOURCE_AUTHORITY; federation policy authorized but no admissible member source yet.",
        "CHECKED_AT_UTC": "2026-08-09T06:10:00Z",
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
            "Broader Gate discovery still unresolved for clinical laboratory FACILITIES: "
            "IRIMC = professional persons (not facilities); "
            "ISIRI 17025 = calibration/testing labs (not clinical iran_laboratories); "
            "MoH laboratory office portals (e.g. ircme.ir continuing-education lists) are not clinical facility directories; "
            "commercial lab portals (e-teb/avval/irindex) are Tier-3 discovery-only."
        ),
        "notes": "CAP24 BLOCKED_SOURCE_AUTHORITY; do not map IRIMC persons into iran_laboratories.",
        "CHECKED_AT_UTC": "2026-08-09T06:10:00Z",
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
