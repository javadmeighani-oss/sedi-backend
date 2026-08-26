"""Wave02 D01–D17 URL → coverage identity (acquisition/provenance only).

Does NOT grant specialized serving eligibility. MedlinePlus/NIMH global low-risk
remains NO. Specialized eligibility stays D18/D19-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Wave02CoverageIdentity:
    entity_id: str
    domain: str
    topic: str
    disease_or_condition: str
    jurisdiction: str = "US"


# Needle (lowercased substring of canonical URL) → coverage identity.
# Order matters for first-match; keep more-specific needles before broad ones.
_WAVE02_URL_COVERAGE: tuple[tuple[str, Wave02CoverageIdentity], ...] = (
    ("cancers.html", Wave02CoverageIdentity("D01", "disease_clinical", "oncology", "cancer")),
    ("lungdiseases.html", Wave02CoverageIdentity("D02", "disease_clinical", "respiratory", "lung disease")),
    ("kidneydiseases.html", Wave02CoverageIdentity("D03", "disease_clinical", "renal", "kidney disease")),
    ("digestivediseases.html", Wave02CoverageIdentity("D04", "disease_clinical", "gastroenterology", "digestive disease")),
    ("arthritis.html", Wave02CoverageIdentity("D05", "disease_clinical", "musculoskeletal", "arthritis")),
    ("skincancer.html", Wave02CoverageIdentity("D06", "disease_clinical", "dermatology", "skin cancer")),
    ("eyediseases.html", Wave02CoverageIdentity("D07", "disease_clinical", "ophthalmology", "eye disease")),
    ("hearingdisordersanddeafness.html", Wave02CoverageIdentity("D08", "disease_clinical", "hearing", "hearing disorders")),
    ("dentalhealth.html", Wave02CoverageIdentity("D09", "disease_clinical", "oral_health", "dental health")),
    ("womenshealth.html", Wave02CoverageIdentity("D10", "disease_clinical", "womens_health", "women's health")),
    ("childrenshealth.html", Wave02CoverageIdentity("D11", "disease_clinical", "pediatrics", "children's health")),
    ("olderadulthealth.html", Wave02CoverageIdentity("D12", "disease_clinical", "geriatrics", "older adult health")),
    ("infectiousdiseases.html", Wave02CoverageIdentity("D13", "disease_clinical", "infectious", "infectious diseases")),
    ("rarediseases.html", Wave02CoverageIdentity("D14", "disease_clinical", "rare_disease", "rare diseases")),
    ("rehabilitation.html", Wave02CoverageIdentity("D15", "disease_clinical", "rehabilitation", "rehabilitation")),
    ("palliativecare.html", Wave02CoverageIdentity("D16", "disease_clinical", "palliative", "palliative care")),
    ("cdc.gov/niosh", Wave02CoverageIdentity("D17", "environmental_occupational", "occupational_health", "environmental and occupational health")),
    ("/niosh/", Wave02CoverageIdentity("D17", "environmental_occupational", "occupational_health", "environmental and occupational health")),
    ("heartdiseases.html", Wave02CoverageIdentity("", "cardiovascular", "heart", "heart disease")),
    ("diabetes.html", Wave02CoverageIdentity("", "diabetes_metabolic", "diabetes", "diabetes")),
    ("nutrition.html", Wave02CoverageIdentity("", "nutrition", "nutrition", "nutrition")),
    ("sleepdisorders.html", Wave02CoverageIdentity("", "lifestyle_prevention_routines", "sleep", "sleep disorders")),
    ("healthyliving.html", Wave02CoverageIdentity("", "lifestyle_prevention_routines", "healthy_living", "healthy living")),
    ("healthy-weight", Wave02CoverageIdentity("D12", "lifestyle", "healthy_weight", "healthy weight", "GB")),
    ("quit-smoking", Wave02CoverageIdentity("", "lifestyle", "quit_smoking", "quit smoking", "GB")),
    ("alcohol-advice", Wave02CoverageIdentity("", "lifestyle", "alcohol", "alcohol advice", "GB")),
    ("seasonal-health", Wave02CoverageIdentity("", "lifestyle", "seasonal_health", "seasonal health", "GB")),
    ("anxiety-disorders", Wave02CoverageIdentity("", "mental_health_psychology", "anxiety", "anxiety disorders")),
    ("caring-for-your-mental-health", Wave02CoverageIdentity("", "mental_health_psychology", "mental_health_self_care", "mental health self-care")),
)


def resolve_wave02_coverage_from_url(url: str | None) -> Optional[Wave02CoverageIdentity]:
    if not url:
        return None
    low = str(url).strip().lower()
    if not low:
        return None
    for needle, identity in _WAVE02_URL_COVERAGE:
        if needle in low:
            return identity
    return None


__all__ = [
    "Wave02CoverageIdentity",
    "resolve_wave02_coverage_from_url",
]
