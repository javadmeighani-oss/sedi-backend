"""Governed specialized D18/D19 serving eligibility (not global MedlinePlus low-risk).

Granularity: source_key + entity identity (URL / manifest_entity_id / clinical tokens)
+ content-quality gate. MedlinePlus ``governed_low_risk_eligibility`` remains NO.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
    ReviewState,
)
from backend.app.services.i5.medical_safety_gate import assert_allowed_medical_safety_transition
from backend.app.services.i5.trusted_source_manifest import (
    manifest_row_for_key,
)

PACKAGE_ID = "I5-SPECIALIZED-ENTITY-ELIGIBILITY-V1"
SPECIALIZED_SOURCE_KEY = "medlineplus_consumer_health"

_NAV_CHROME_MARKERS = (
    "skip to main content",
    "skip directly to",
    "skip to search",
    "search the nhs website",
    "browse more home",
    "official website of the united states",
    "here's how you know",
    "an official website of the united states government",
    "javascript must be enabled",
    "enable cookies",
    "share this page",
    "page last updated",
    "get email updates",
)


@dataclass(frozen=True)
class SpecializedEntitySpec:
    entity_id: str
    alias: str
    track_id: str
    domain: str
    topic: str
    url_needles: tuple[str, ...]
    clinical_tokens: tuple[str, ...]
    disease_label: str


D18 = SpecializedEntitySpec(
    entity_id="D18",
    alias="ALS",
    track_id="ALS-TRACK",
    domain="neurology_als",
    topic="als",
    url_needles=("amyotrophiclateralsclerosis",),
    clinical_tokens=(
        "amyotrophic",
        "lateral sclerosis",
        "motor neuron",
        "motor neurone",
        "als",
        "lou gehrig",
    ),
    disease_label="amyotrophic lateral sclerosis",
)

D19 = SpecializedEntitySpec(
    entity_id="D19",
    alias="MS",
    track_id="MS-TRACK",
    domain="neurology_ms",
    topic="ms",
    url_needles=("multiplesclerosis",),
    clinical_tokens=(
        "multiple sclerosis",
        "ms is",
        "demyelinat",
        "optic neuritis",
        "relapsing",
    ),
    disease_label="multiple sclerosis",
)

SPECIALIZED_SPECS: tuple[SpecializedEntitySpec, ...] = (D18, D19)
SPECIALIZED_BY_ID = {s.entity_id: s for s in SPECIALIZED_SPECS}


class SpecializedEligibilityError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


def resolve_specialized_entity_from_url(url: Optional[str]) -> Optional[SpecializedEntitySpec]:
    sample = (url or "").casefold()
    if not sample:
        return None
    for spec in SPECIALIZED_SPECS:
        if any(needle in sample for needle in spec.url_needles):
            return spec
    return None


def _activation_yes(value: Any) -> bool:
    if value is True:
        return True
    return str(value or "").strip().upper() in {"YES", "TRUE", "1"}


def statement_dominated_by_nav_chrome(statement: Optional[str]) -> bool:
    text = (statement or "").strip()
    if len(text) < 40:
        return True
    sample = text.casefold()
    chrome_hits = sum(1 for marker in _NAV_CHROME_MARKERS if marker in sample)
    clinical_hits = 0
    for spec in SPECIALIZED_SPECS:
        clinical_hits += sum(1 for tok in spec.clinical_tokens if tok in sample)
    # Chrome-heavy and lacking clinical identity → reject for serving.
    if chrome_hits >= 2 and clinical_hits == 0:
        return True
    # Leading chrome prefix without clinical tokens in first 180 chars.
    head = sample[:180]
    head_chrome = sum(1 for marker in _NAV_CHROME_MARKERS if marker in head)
    if head_chrome >= 2 and clinical_hits == 0:
        return True
    return False


def statement_has_clinical_identity(statement: Optional[str], spec: SpecializedEntitySpec) -> bool:
    sample = (statement or "").casefold()
    return any(tok in sample for tok in spec.clinical_tokens)


def content_quality_pass(statement: Optional[str], spec: SpecializedEntitySpec) -> tuple[bool, str]:
    text = (statement or "").strip()
    if len(text) < 80:
        return False, "STATEMENT_TOO_SHORT"
    if statement_dominated_by_nav_chrome(text):
        return False, "NAV_CHROME_DOMINATED"
    if not statement_has_clinical_identity(text, spec):
        return False, "MISSING_CLINICAL_IDENTITY"
    # Fail closed on prescription/diagnosis expansion cues in serving statement.
    banned = ("take this medication", "you have als", "you have ms", "i diagnose", "prescribe ")
    low = text.casefold()
    if any(b in low for b in banned):
        return False, "DIAGNOSIS_PRESCRIPTION_EXPANSION"
    return True, "OK"


def infer_specialized_spec_for_ku(
    ku: Any,
    *,
    canonical_url: Optional[str] = None,
) -> Optional[SpecializedEntitySpec]:
    entity = str(getattr(ku, "manifest_entity_id", None) or "").strip().upper()
    if entity in SPECIALIZED_BY_ID:
        return SPECIALIZED_BY_ID[entity]
    from_url = resolve_specialized_entity_from_url(canonical_url)
    if from_url is not None:
        return from_url
    disease = str(getattr(ku, "disease_or_health_condition", None) or "").casefold()
    statement = str(getattr(ku, "normalized_statement", None) or "").casefold()
    topic = str(getattr(ku, "topic_taxonomy", None) or "").casefold()
    blob = f"{disease} {statement} {topic}"
    for spec in SPECIALIZED_SPECS:
        if any(tok in blob for tok in spec.clinical_tokens):
            return spec
        if any(needle in blob for needle in spec.url_needles):
            return spec
    return None


def specialized_source_authorized(source_key: str) -> bool:
    if source_key != SPECIALIZED_SOURCE_KEY:
        return False
    row = manifest_row_for_key(source_key)
    if row is None or not _activation_yes(row.get("activation")):
        return False
    rights = str(row.get("rights_terms_state") or "").upper()
    robots = str(row.get("robots_access_state") or "").upper()
    if rights not in {"PUBLIC_DOMAIN", "OGL", "APPROVED", "ACCEPTABLE"}:
        return False
    if robots != "ALLOWED":
        return False
    # Global low-risk must remain NO for this source.
    low = str(row.get("governed_low_risk_eligibility") or "NO").strip().upper()
    if low in {"YES", "TRUE", "1"}:
        # Hard fail-closed: specialized path must not coexist with global YES.
        return False
    entities = {str(e).strip().upper() for e in (row.get("entity_coverage") or [])}
    return "D18" in entities and "D19" in entities


def can_apply_specialized_entity_eligibility(
    *,
    source_key: str,
    ku: Any,
    canonical_url: Optional[str] = None,
) -> tuple[bool, str, Optional[SpecializedEntitySpec]]:
    if not specialized_source_authorized(source_key):
        return False, "SOURCE_NOT_AUTHORIZED_FOR_SPECIALIZED", None
    if not bool(getattr(ku, "provenance_complete", False)):
        return False, "PROVENANCE_INCOMPLETE", None
    if getattr(ku, "retraction_reason", None):
        return False, "RETRACTED", None
    conflict = str(getattr(ku, "conflict_state", "") or ConflictState.NONE.value)
    if conflict not in {ConflictState.NONE.value, ConflictState.RESOLVED.value}:
        return False, "CONFLICT_BLOCK", None
    spec = infer_specialized_spec_for_ku(ku, canonical_url=canonical_url)
    if spec is None:
        return False, "ENTITY_IDENTITY_MISSING", None
    url = (canonical_url or "").casefold()
    if url and not any(n in url for n in spec.url_needles):
        # URL present but not the disease page — fail closed (prevent heart/diabetes pages).
        return False, "URL_NOT_IN_ENTITY_SCOPE", None
    ok, reason = content_quality_pass(getattr(ku, "normalized_statement", None), spec)
    if not ok:
        return False, reason, spec
    return True, "OK", spec


def apply_specialized_entity_fields(
    ku: Any,
    *,
    source_key: str,
    canonical_url: Optional[str] = None,
) -> tuple[bool, str]:
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=source_key,
        ku=ku,
        canonical_url=canonical_url,
    )
    if not allowed or spec is None:
        return False, reason

    prior_medical = getattr(ku, "medical_safety_state", None) or MedicalSafetyState.UNKNOWN.value
    # Allowed path: UNKNOWN→PENDING_REVIEW→CLEARED or PENDING_REVIEW→CLEARED.
    if str(prior_medical) == MedicalSafetyState.UNKNOWN.value:
        assert_allowed_medical_safety_transition(prior_medical, MedicalSafetyState.PENDING_REVIEW)
        ku.medical_safety_state = MedicalSafetyState.PENDING_REVIEW.value
        prior_medical = MedicalSafetyState.PENDING_REVIEW.value
    assert_allowed_medical_safety_transition(prior_medical, MedicalSafetyState.CLEARED)

    ku.manifest_entity_id = spec.entity_id
    ku.manifest_track_id = spec.track_id
    ku.disease_or_health_condition = spec.disease_label
    ku.domain = spec.domain
    ku.topic_taxonomy = spec.topic
    ku.evidence_strength = EvidenceStrength.MODERATE.value
    ku.freshness_state = FreshnessState.CURRENT.value
    ku.medical_safety_state = MedicalSafetyState.CLEARED.value
    ku.conflict_state = ConflictState.NONE.value
    ku.review_state = ReviewState.APPROVED.value
    ku.publication_state = PublicationState.PUBLISHED.value
    ku.applicability = "consumer_health_education_not_diagnosis"
    return True, "OK"


def strip_html_nav_chrome(text: str) -> str:
    """Bounded self-heal: drop leading chrome; keep first clinical-bearing window."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return raw
    sample = raw.casefold()
    cut = 0
    for marker in _NAV_CHROME_MARKERS:
        idx = sample.find(marker)
        if idx == 0 or (0 <= idx <= 40):
            cut = max(cut, idx + len(marker))
    # Prefer start at first clinical token when present.
    clinical_start = None
    for spec in SPECIALIZED_SPECS:
        for tok in spec.clinical_tokens:
            idx = sample.find(tok)
            if idx >= 0:
                clinical_start = idx if clinical_start is None else min(clinical_start, idx)
    if clinical_start is not None and clinical_start > 0:
        # Include a little left context but skip pure chrome heads.
        start = clinical_start
        cleaned = raw[start:].strip()
        if len(cleaned) >= 80:
            return cleaned
    if cut > 0 and cut < len(raw):
        cleaned = raw[cut:].strip(" -:|")
        if len(cleaned) >= 80:
            return cleaned
    return raw


def provenance_canonical_url(prov: Any) -> Optional[str]:
    if prov is None:
        return None
    # attribution_data may embed source_url
    blob = getattr(prov, "attribution_data", None)
    if blob:
        try:
            data = json.loads(blob) if isinstance(blob, str) else blob
            if isinstance(data, dict):
                url = data.get("source_url") or data.get("url")
                if url:
                    return str(url)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    cite = getattr(prov, "citation_rendering_data", None)
    if cite:
        try:
            data = json.loads(cite) if isinstance(cite, str) else cite
            if isinstance(data, dict) and data.get("url"):
                return str(data["url"])
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return None


__all__ = [
    "PACKAGE_ID",
    "SPECIALIZED_SOURCE_KEY",
    "D18",
    "D19",
    "SPECIALIZED_SPECS",
    "SpecializedEntitySpec",
    "SpecializedEligibilityError",
    "resolve_specialized_entity_from_url",
    "statement_dominated_by_nav_chrome",
    "content_quality_pass",
    "infer_specialized_spec_for_ku",
    "specialized_source_authorized",
    "can_apply_specialized_entity_eligibility",
    "apply_specialized_entity_fields",
    "strip_html_nav_chrome",
    "provenance_canonical_url",
    "KnowledgeUnitRuntimeEligibility",
]
