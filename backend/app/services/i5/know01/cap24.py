"""CAP24 Iran Laboratories authority status (KNOW-01 evidence pack)."""

from __future__ import annotations

from typing import Any, Dict, List

# Prefer exact blocked evidence over fabricated directory authority.
CAP24_STATUS = "BLOCKED_WITH_EXACT_EVIDENCE"
CAP24_PRIMARY_AUTHORITY_FOUND = False
CAP24_AUTHORITY_QUALITY = "UNVERIFIED_NATIONWIDE"
CAP24_MACHINE_READABLE = False
CAP24_RIGHTS_VERIFIED = False
CAP24_AUTOMATION_PATH = "NONE"
CAP24_DATA_SCOPE = "clinical_diagnostic_laboratories_pathology_genetics_reference_public_health"
CAP24_BLOCKER = (
    "No verified nationwide machine-readable clinical diagnostic laboratory authority "
    "with clear automation/TDM rights was confirmed in KNOW-01 controlled research scope. "
    "Commercial directories are not primary credential authority."
)

CAP24_AUTHORITY_CANDIDATES: List[Dict[str, Any]] = [
    {
        "name": "Iran MoHME / laboratory regulation pages",
        "authority_class": "IRAN_REFERENCE_LAB_AUTHORITY",
        "official_or_secondary": "OFFICIAL_CANDIDATE",
        "credential_authority": "UNKNOWN",
        "canonical_endpoint": "https://behdasht.gov.ir",
        "automation_allowed": "UNKNOWN",
        "evidence_class": "UNVERIFIED",
        "notes": "Candidate homepage family only; bulk lab directory not confirmed",
    },
    {
        "name": "Medical university facility directories",
        "authority_class": "IRAN_MEDICAL_UNIVERSITY",
        "official_or_secondary": "OFFICIAL_CANDIDATE",
        "credential_authority": "NO",
        "canonical_endpoint": None,
        "automation_allowed": "UNKNOWN",
        "evidence_class": "INFERENCE",
        "notes": "May list affiliated labs locally; not nationwide primary",
    },
    {
        "name": "Commercial lab appointment/directory sites",
        "authority_class": "COMMERCIAL_DIRECTORY",
        "official_or_secondary": "SECONDARY",
        "credential_authority": "NO",
        "canonical_endpoint": None,
        "automation_allowed": "UNKNOWN",
        "evidence_class": "FACT",
        "notes": "Must never silently become primary licensing/credential authority",
    },
]

CAP24_PRIMARY_AUTHORITY = None
CAP24_SECONDARY_CORROBORATION = [c for c in CAP24_AUTHORITY_CANDIDATES if c["official_or_secondary"] == "SECONDARY"]
CAP24_ACCESS_ROUTE = "NONE_VERIFIED_MACHINE_READABLE"
CAP24_AUTOMATION_RIGHTS = "UNKNOWN_FAIL_CLOSED"
CAP24_DATA_FIELDS = [
    "facility_name",
    "lab_class",
    "province",
    "city",
    "licence_id_if_public",
    "accreditation_if_public",
]
CAP24_BLOCKERS = [
    CAP24_BLOCKER,
    "UNKNOWN rights remain FAIL-CLOSED",
    "Drug/food QC labs are not interchangeable with clinical diagnostic labs",
]


def cap24_evidence_pack() -> Dict[str, Any]:
    return {
        "CAP24_STATUS": CAP24_STATUS,
        "CAP24_PRIMARY_AUTHORITY_FOUND": CAP24_PRIMARY_AUTHORITY_FOUND,
        "CAP24_AUTHORITY_QUALITY": CAP24_AUTHORITY_QUALITY,
        "CAP24_MACHINE_READABLE": CAP24_MACHINE_READABLE,
        "CAP24_RIGHTS_VERIFIED": CAP24_RIGHTS_VERIFIED,
        "CAP24_AUTOMATION_PATH": CAP24_AUTOMATION_PATH,
        "CAP24_DATA_SCOPE": CAP24_DATA_SCOPE,
        "CAP24_BLOCKER": CAP24_BLOCKER,
        "CAP24_AUTHORITY_CANDIDATES": CAP24_AUTHORITY_CANDIDATES,
        "CAP24_PRIMARY_AUTHORITY": CAP24_PRIMARY_AUTHORITY,
        "CAP24_SECONDARY_CORROBORATION": CAP24_SECONDARY_CORROBORATION,
        "CAP24_ACCESS_ROUTE": CAP24_ACCESS_ROUTE,
        "CAP24_AUTOMATION_RIGHTS": CAP24_AUTOMATION_RIGHTS,
        "CAP24_DATA_FIELDS": CAP24_DATA_FIELDS,
        "CAP24_BLOCKERS": CAP24_BLOCKERS,
        "FACT": [
            "Iran clinical lab directory remains an operational authority problem (CAP24)",
            "Commercial directories are not credential authority",
        ],
        "INFERENCE": [
            "University directories may provide local corroboration only",
        ],
        "UNVERIFIED": [
            "Nationwide machine-readable MoH lab export",
            "Automation/TDM rights for any candidate bulk feed",
        ],
        "REVIEW_REQUIRED": True,
    }
