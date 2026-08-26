"""Governed specialized entity serving eligibility (not global source low-risk).

Granularity: source_key + entity identity (URL / manifest_entity_id / clinical tokens)
+ content-quality gate. MedlinePlus ``governed_low_risk_eligibility`` remains NO.
NIOSH D17 uses the same specialized pattern with low-risk NO.
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
# Historical alias — MedlinePlus remains the D18/D19 specialized source.
SPECIALIZED_SOURCE_KEY = "medlineplus_consumer_health"
NIOSH_SOURCE_KEY = "niosh_occupational"

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

D17 = SpecializedEntitySpec(
    entity_id="D17",
    alias="ENV_OCC",
    track_id="D17-TRACK",
    domain="environmental_occupational",
    topic="occupational_health",
    url_needles=("cdc.gov/niosh", "/niosh/"),
    clinical_tokens=(
        "niosh",
        "occupational",
        "workplace",
        "worker",
        "exposure",
        "chemical",
        "noise",
        "outdoor",
        "safety and health",
    ),
    disease_label="environmental and occupational health",
)

# More-specific URL needles first (resolve_specialized_entity_from_url is first-match).
D16 = SpecializedEntitySpec(
    entity_id="D16",
    alias="PALLIATIVE",
    track_id="D16-TRACK",
    domain="palliative",
    topic="palliative_care",
    url_needles=("advanced-cancer/care-choices", "about-cancer/coping"),
    clinical_tokens=("palliative", "hospice", "advanced cancer", "end of life", "coping", "supportive care"),
    disease_label="palliative care",
)

D01 = SpecializedEntitySpec(
    entity_id="D01",
    alias="ONCOLOGY",
    track_id="D01-TRACK",
    domain="oncology",
    topic="cancer",
    url_needles=("cancer.gov/publications/pdq", "about-cancer/treatment", "cancer.gov/types/"),
    clinical_tokens=("cancer", "tumor", "oncology", "pdq", "chemotherapy", "radiation"),
    disease_label="oncology and supportive cancer care",
)

D06 = SpecializedEntitySpec(
    entity_id="D06",
    alias="DERM",
    track_id="D06-TRACK",
    domain="dermatology",
    topic="skin_health",
    url_needles=("health-topics/skin-diseases", "skin-diseases"),
    clinical_tokens=("skin", "dermatology", "rash", "eczema", "psoriasis"),
    disease_label="dermatology and skin health",
)

D05 = SpecializedEntitySpec(
    entity_id="D05",
    alias="MSK",
    track_id="D05-TRACK",
    domain="musculoskeletal",
    topic="arthritis_msk",
    url_needles=("health-topics/arthritis", "niams.nih.gov/health-topics"),
    clinical_tokens=("arthritis", "joint", "musculoskeletal", "bone", "rheumat"),
    disease_label="musculoskeletal health and pain",
)

D03 = SpecializedEntitySpec(
    entity_id="D03",
    alias="KIDNEY",
    track_id="D03-TRACK",
    domain="renal",
    topic="kidney",
    url_needles=("kidney-disease",),
    clinical_tokens=("kidney", "renal", "dialysis", "urine", "nephro"),
    disease_label="kidney and urinary tract health",
)

D04 = SpecializedEntitySpec(
    entity_id="D04",
    alias="GI_LIVER",
    track_id="D04-TRACK",
    domain="gastroenterology",
    topic="digestive_liver",
    url_needles=("liver-disease", "digestive-diseases"),
    clinical_tokens=("liver", "digestive", "hepatitis", "gastro", "bowel"),
    disease_label="gastroenterology and digestive health",
)

D02 = SpecializedEntitySpec(
    entity_id="D02",
    alias="RESP",
    track_id="D02-TRACK",
    domain="respiratory",
    topic="lung_health",
    url_needles=("nhlbi.nih.gov/health",),
    clinical_tokens=("asthma", "copd", "lung", "respiratory", "breathing", "airway"),
    disease_label="respiratory health and diseases",
)

D07 = SpecializedEntitySpec(
    entity_id="D07",
    alias="EYE",
    track_id="D07-TRACK",
    domain="ophthalmology",
    topic="eye_health",
    url_needles=("nei.nih.gov/learn-about-eye-health",),
    clinical_tokens=("eye", "vision", "ophthalm", "retina", "glaucoma", "cataract"),
    disease_label="ophthalmology and vision",
)

D09 = SpecializedEntitySpec(
    entity_id="D09",
    alias="ORAL",
    track_id="D09-TRACK",
    domain="dental",
    topic="oral_health",
    url_needles=("nidcr.nih.gov/health-info",),
    clinical_tokens=("oral", "dental", "tooth", "teeth", "gum", "cavity", "decay"),
    disease_label="oral and dental health",
)

D08 = SpecializedEntitySpec(
    entity_id="D08",
    alias="HEARING",
    track_id="D08-TRACK",
    domain="ent_hearing",
    topic="hearing_balance",
    url_needles=("nidcd.nih.gov/health",),
    clinical_tokens=("hearing", "ear", "vestibular", "balance", "deaf", "tinnitus", "audiolog"),
    disease_label="ear, hearing and vestibular health",
)

D10 = SpecializedEntitySpec(
    entity_id="D10",
    alias="WOMENS_HEALTH",
    track_id="D10-TRACK",
    domain="womens_health",
    topic="womens_reproductive",
    url_needles=("womenshealth.gov",),
    clinical_tokens=("women", "pregnancy", "maternal", "reproductive", "menopause", "breast"),
    disease_label="women's health and reproductive health",
)

D11 = SpecializedEntitySpec(
    entity_id="D11",
    alias="CHILD_DEV",
    track_id="D11-TRACK",
    domain="pediatrics",
    topic="child_development",
    url_needles=("cdc.gov/child-development", "ncbddd/childdevelopment", "childdevelopment"),
    clinical_tokens=("child", "infant", "toddler", "development", "milestone", "pediatric"),
    disease_label="pediatrics and adolescent health",
)

D13 = SpecializedEntitySpec(
    entity_id="D13",
    alias="INFECTIOUS",
    track_id="D13-TRACK",
    domain="infectious",
    topic="infectious_diseases",
    url_needles=("cdc.gov/ncezid", "/ncezid/"),
    clinical_tokens=("infectious", "infection", "virus", "bacteria", "outbreak", "pathogen", "ncezid"),
    disease_label="infectious diseases beyond hepatitis",
)

D14 = SpecializedEntitySpec(
    entity_id="D14",
    alias="RARE",
    track_id="D14-TRACK",
    domain="rare_disease",
    topic="rare_diseases",
    url_needles=("rarediseases.info.nih.gov",),
    clinical_tokens=("rare", "genetic", "orphan", "gard", "inherited", "disorder"),
    disease_label="rare diseases",
)

D15 = SpecializedEntitySpec(
    entity_id="D15",
    alias="REHAB",
    track_id="D15-TRACK",
    domain="rehabilitation",
    topic="rehabilitation",
    url_needles=("nichd.nih.gov/health",),
    clinical_tokens=("rehabilit", "recovery", "function", "therapy", "disability", "child health"),
    disease_label="rehabilitation and functional recovery",
)

# Specific-first ordering for URL first-match.
SPECIALIZED_SPECS: tuple[SpecializedEntitySpec, ...] = (
    D16,
    D01,
    D06,
    D05,
    D03,
    D04,
    D02,
    D07,
    D09,
    D08,
    D10,
    D11,
    D13,
    D14,
    D15,
    D17,
    D18,
    D19,
)
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


def specialized_allowed_entities_for_source(source_key: str) -> set[str]:
    row = manifest_row_for_key(source_key)
    if row is None or not _activation_yes(row.get("activation")):
        return set()
    rights = str(row.get("rights_terms_state") or "").upper()
    robots = str(row.get("robots_access_state") or "").upper()
    if rights not in {"PUBLIC_DOMAIN", "OGL", "APPROVED", "ACCEPTABLE"}:
        return set()
    if robots != "ALLOWED":
        return set()
    low = str(row.get("governed_low_risk_eligibility") or "NO").strip().upper()
    if low in {"YES", "TRUE", "1"}:
        # Specialized path must not coexist with global low-risk YES.
        return set()
    explicit = {
        str(e).strip().upper()
        for e in (row.get("specialized_serving_eligibility") or [])
        if str(e).strip()
    }
    if explicit:
        return explicit
    # Backward-compatible MedlinePlus fallback.
    if source_key == SPECIALIZED_SOURCE_KEY:
        entities = {str(e).strip().upper() for e in (row.get("entity_coverage") or [])}
        if "D18" in entities and "D19" in entities:
            return {"D18", "D19"}
    return set()


def _clinical_token_hit(tok: str, sample: str) -> bool:
    """Avoid short-token false positives (e.g. 'ear' inside 'search')."""
    t = (tok or "").casefold().strip()
    if not t:
        return False
    if " " in t or len(t) >= 5:
        return t in sample
    return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", sample) is not None


def statement_dominated_by_nav_chrome(statement: Optional[str]) -> bool:
    text = (statement or "").strip()
    if len(text) < 40:
        return True
    sample = text.casefold()
    chrome_hits = sum(1 for marker in _NAV_CHROME_MARKERS if marker in sample)
    clinical_hits = 0
    for spec in SPECIALIZED_SPECS:
        clinical_hits += sum(1 for tok in spec.clinical_tokens if _clinical_token_hit(tok, sample))
    if chrome_hits >= 2 and clinical_hits == 0:
        return True
    head = sample[:180]
    head_chrome = sum(1 for marker in _NAV_CHROME_MARKERS if marker in head)
    if head_chrome >= 2 and clinical_hits == 0:
        return True
    return False


def statement_has_clinical_identity(statement: Optional[str], spec: SpecializedEntitySpec) -> bool:
    sample = (statement or "").casefold()
    return any(_clinical_token_hit(tok, sample) for tok in spec.clinical_tokens)


def content_quality_pass(statement: Optional[str], spec: SpecializedEntitySpec) -> tuple[bool, str]:
    text = (statement or "").strip()
    if len(text) < 80:
        return False, "STATEMENT_TOO_SHORT"
    if statement_dominated_by_nav_chrome(text):
        return False, "NAV_CHROME_DOMINATED"
    if not statement_has_clinical_identity(text, spec):
        return False, "MISSING_CLINICAL_IDENTITY"
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
        if any(_clinical_token_hit(tok, blob) for tok in spec.clinical_tokens):
            return spec
        if any(needle in blob for needle in spec.url_needles):
            return spec
    return None


def specialized_source_authorized(source_key: str) -> bool:
    return bool(specialized_allowed_entities_for_source(source_key))


def can_apply_specialized_entity_eligibility(
    *,
    source_key: str,
    ku: Any,
    canonical_url: Optional[str] = None,
) -> tuple[bool, str, Optional[SpecializedEntitySpec]]:
    allowed_entities = specialized_allowed_entities_for_source(source_key)
    if not allowed_entities:
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
    if spec.entity_id not in allowed_entities:
        return False, "ENTITY_NOT_AUTHORIZED_FOR_SOURCE", None
    url = (canonical_url or "").casefold()
    if url and not any(n in url for n in spec.url_needles):
        return False, "URL_NOT_IN_ENTITY_SCOPE", None
    if "/niosh/archive/" in url:
        return False, "ROBOTS_DISALLOW_ARCHIVE", None
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
    clinical_start = None
    for spec in SPECIALIZED_SPECS:
        for tok in spec.clinical_tokens:
            idx = sample.find(tok)
            if idx >= 0:
                clinical_start = idx if clinical_start is None else min(clinical_start, idx)
    if clinical_start is not None and clinical_start > 0:
        cleaned = raw[clinical_start:].strip()
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
    "NIOSH_SOURCE_KEY",
    "D01",
    "D02",
    "D03",
    "D04",
    "D05",
    "D06",
    "D07",
    "D09",
    "D16",
    "D17",
    "D18",
    "D19",
    "SPECIALIZED_SPECS",
    "SpecializedEntitySpec",
    "SpecializedEligibilityError",
    "resolve_specialized_entity_from_url",
    "specialized_allowed_entities_for_source",
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
