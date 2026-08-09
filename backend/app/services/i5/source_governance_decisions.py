"""Permanent I5 source-governance decisions ratified for V1.

DIRECT_PUBLISHER_PERMISSION_IS_NOT_A_UNIVERSAL_PREREQUISITE
PUBLIC_WEB_INTERNAL_FACT_EVIDENCE_DISTILLATION = ALLOWED_WITH_GOVERNANCE
FEDERATED_OFFICIAL_PROVIDER_WEB_SOURCE = ALLOWED_WITH_GOVERNANCE (directory facts only)
"""
from __future__ import annotations

from typing import Any

GATE_RATIFICATION_ID = (
    "I5-FINAL-REMEDIATION-AND-OPERATIONAL-CLOSURE-MASTER-GATE-02"
)

DIRECT_PUBLISHER_PERMISSION_IS_NOT_A_UNIVERSAL_PREREQUISITE = True
PUBLIC_WEB_INTERNAL_FACT_EVIDENCE_DISTILLATION = "ALLOWED_WITH_GOVERNANCE"
FEDERATED_OFFICIAL_PROVIDER_WEB_SOURCE = "ALLOWED_WITH_GOVERNANCE"

# Dual decision axes — both required.
CRAWLER_ACCESS_ADMISSIBLE = "CRAWLER_ACCESS_ADMISSIBILITY"
CONTENT_USE_ADMISSIBLE = "CONTENT_USE_ADMISSIBILITY"

INTERNAL_FACT_EVIDENCE_DISTILLATION_MODE = {
    "mode": "INTERNAL_FACT_EVIDENCE_DISTILLATION",
    "may": (
        "fetch_permitted_public_page",
        "parse_structured_or_plain_facts",
        "normalize_facts",
        "create_structured_evidence",
        "create_rewritten_paraphrased_summaries",
        "extract_health_concepts",
        "attach_source_provenance",
        "record_observation_timestamp",
        "record_canonical_url",
        "record_publisher_identity",
        "record_content_hash_when_architecture_permits",
        "version_diff_future_observations",
        "link_knowledge_to_originating_source",
    ),
    "must_not": (
        "copy_entire_copyrighted_articles",
        "mirror_whole_websites",
        "save_images_videos_unless_independently_admissible",
        "reproduce_substantial_copyrighted_expression",
        "remove_attribution",
        "bypass_technical_restrictions",
        "impersonate_authenticated_users",
        "bypass_captcha",
        "bypass_login",
        "bypass_paywall",
        "bypass_robots",
        "defeat_anti_bot_controls",
        "scrape_personal_patient_private_data",
    ),
    "preferred_for_non_explicit_reuse": "FACTS_PLUS_REWRITTEN_STRUCTURED_KNOWLEDGE_PLUS_PROVENANCE",
}

FAIL_CLOSED_WHEN = (
    "robots_explicitly_disallows_path",
    "terms_expressly_prohibit_intended_automated_access_or_use",
    "authentication_required",
    "captcha_bypass_required",
    "paywall_bypass_required",
    "personal_private_data_would_be_collected",
    "rights_materially_unresolved",
    "source_identity_cannot_be_established",
)


def evaluate_source_admissibility(row: dict[str, Any]) -> dict[str, Any]:
    """Return CRAWLER_ACCESS + CONTENT_USE decisions without inventing permission."""
    crawler_ok = bool(row.get("PUBLIC_ACCESS")) and not bool(row.get("AUTHENTICATION_REQUIRED"))
    crawler_ok = crawler_ok and not bool(row.get("CAPTCHA_PRESENT")) and not bool(row.get("PAYWALL_PRESENT"))
    crawler_ok = crawler_ok and not bool(row.get("AUTOMATION_PROHIBITION_FOUND"))
    robots = str(row.get("ROBOTS_CHECK_RESULT") or "")
    if "DISALLOW" in robots.upper() and "ALLOW" not in robots.upper():
        # Narrow heuristic only when robots result is an explicit deny-all style.
        crawler_ok = False
    content_ok = bool(row.get("FACTS_ONLY_EXTRACTION", True)) and not bool(row.get("PATIENT_DATA_PRESENT"))
    content_ok = content_ok and bool(row.get("RIGHTS_BASIS"))
    final = crawler_ok and content_ok and bool(row.get("ALLOWED_FOR_V1_POPULATION"))
    return {
        CRAWLER_ACCESS_ADMISSIBLE: crawler_ok,
        CONTENT_USE_ADMISSIBLE: content_ok,
        "FINAL_ADMISSIBILITY": final,
        "CONTENT_USE_MODE": row.get("CONTENT_USE_MODE")
        or INTERNAL_FACT_EVIDENCE_DISTILLATION_MODE["preferred_for_non_explicit_reuse"],
        "NOTE": "Absence of Terms is NOT treated as permission.",
    }
