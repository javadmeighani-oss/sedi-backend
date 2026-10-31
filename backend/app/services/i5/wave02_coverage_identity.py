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
    # R-044 open-licence library (nutrition / exercise / lifestyle sources): explicit topics instead of the sleep default.
    ("medlineplus.gov/antioxidants.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "antioxidants")),
    ("medlineplus.gov/bvitamins.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "bvitamins")),
    ("medlineplus.gov/bodyweight.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "bodyweight")),
    ("medlineplus.gov/caffeine.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "caffeine")),
    ("medlineplus.gov/calcium.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "calcium")),
    ("medlineplus.gov/carbohydrates.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "carbohydrates")),
    ("medlineplus.gov/dasheatingplan.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "dasheatingplan")),
    ("medlineplus.gov/dietaryfats.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "dietaryfats")),
    ("medlineplus.gov/dietaryfiber.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "dietaryfiber")),
    ("medlineplus.gov/dietaryproteins.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "dietaryproteins")),
    ("medlineplus.gov/diets.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "diets")),
    ("medlineplus.gov/drinkingwater.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "drinkingwater")),
    ("medlineplus.gov/foodlabeling.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "foodlabeling")),
    ("medlineplus.gov/foodsafety.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "foodsafety")),
    ("medlineplus.gov/folicacid.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "folicacid")),
    ("medlineplus.gov/iron.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "iron")),
    ("medlineplus.gov/minerals.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "minerals")),
    ("medlineplus.gov/nutritionforolderadults.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "nutritionforolderadults")),
    ("medlineplus.gov/potassium.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "potassium")),
    ("medlineplus.gov/sodium.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "sodium")),
    ("medlineplus.gov/vegetariandiet.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "vegetariandiet")),
    ("medlineplus.gov/vitamina.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "vitamina")),
    ("medlineplus.gov/vitaminc.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "vitaminc")),
    ("medlineplus.gov/vitamind.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "vitamind")),
    ("medlineplus.gov/vitamine.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "vitamine")),
    ("medlineplus.gov/vitamink.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "vitamink")),
    ("medlineplus.gov/vitamins.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "vitamins")),
    ("medlineplus.gov/weightcontrol.html", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "weightcontrol")),
    ("medlineplus.gov/benefitsofexercise.html", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "benefitsofexercise")),
    ("medlineplus.gov/exerciseandphysicalfitness.html", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "exerciseandphysicalfitness")),
    ("medlineplus.gov/exerciseforchildren.html", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "exerciseforchildren")),
    ("medlineplus.gov/exerciseforolderadults.html", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "exerciseforolderadults")),
    ("medlineplus.gov/healthrisksofaninactivelifestyle.html", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "healthrisksofaninactivelifestyle")),
    ("medlineplus.gov/howmuchexercisedoineed.html", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "howmuchexercisedoineed")),
    ("medlineplus.gov/sportsfitness.html", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "sportsfitness")),
    ("medlineplus.gov/ergonomics.html", Wave02CoverageIdentity("", "lifestyle_prevention_routines", "healthy_living", "ergonomics")),
    ("medlineplus.gov/healthyaging.html", Wave02CoverageIdentity("", "lifestyle_prevention_routines", "healthy_living", "healthyaging")),
    ("odphp.health.gov/moveyourway", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "physical activity (Move Your Way)")),
    ("odphp.health.gov/our-work/nutrition-physical-activity/physical-activity-guidelines", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "physical activity guidelines")),
    ("odphp.health.gov/our-work/nutrition-physical-activity/dietary-guidelines", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "dietary guidelines")),
    # Low-risk lifestyle pages: explicit topics (otherwise they fall back to lifestyle/sleep).
    ("nhs.uk/live-well/sleep-and-tiredness", Wave02CoverageIdentity("", "lifestyle", "sleep", "sleep and tiredness", "GB")),
    ("nhs.uk/live-well/exercise", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "physical activity", "GB")),
    ("nhs.uk/live-well/eat-well", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "healthy eating", "GB")),
    ("nhs.uk/live-well/mental-health", Wave02CoverageIdentity("", "wellbeing", "mental_wellbeing", "mental wellbeing", "GB")),
    ("nhs.uk/mental-health/self-help", Wave02CoverageIdentity("", "wellbeing", "mental_wellbeing", "mental wellbeing self-help", "GB")),
    ("cdc.gov/physical-activity-basics", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "physical activity")),
    ("cdc.gov/physical-activity", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "physical activity")),
    ("cdc.gov/physicalactivity", Wave02CoverageIdentity("", "physical_activity_exercise", "exercise", "physical activity")),
    ("cdc.gov/healthy-weight-growth", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "healthy eating and weight")),
    ("cdc.gov/nutrition", Wave02CoverageIdentity("", "nutrition", "healthy_eating", "nutrition")),
    ("nccih.nih.gov/health/meditation", Wave02CoverageIdentity("", "wellbeing", "mindfulness", "meditation and mindfulness")),
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
