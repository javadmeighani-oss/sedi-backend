"""Gate 3 shared constants."""

PROVIDER_CATEGORIES = frozenset({
    "provider_directory", "lab_directory", "local_services", "culture", "sports", "science",
})

TRUST_ORDER = {
    "official": 5,
    "clinical_guideline": 4,
    "vetted_partner": 3,
    "editorial": 2,
    "internal": 1,
}

MIN_TRUST_BY_RISK = {
    "low": "editorial",
    "medium": "editorial",
    "high": "vetted_partner",
    "emergency": None,
}

# Phrases stripped from search queries (reframe, do not block).
RANKING_STRIP_PHRASES = (
    "best doctor", "best lab", "بهترین دکتر", "بهترین آزمایشگاه", "بهترین",
    "the best", "قطعی برو", "حتما برو پیش",
)

# Kept for post-generation output validation (assistant must not claim unsupported ranking).
FORBIDDEN_PROVIDER_PHRASES = RANKING_STRIP_PHRASES

MEDICAL_INTENT_KEYWORDS_FA = (
    "درد", "علائم", "علامت", "دارو", "دوز", "بیماری", "فشار خون", "قلب",
    "آزمایش", "جراحی", "پزشک", "حساسیت", "آلرژی", "تشخیص", "درمان",
)
MEDICAL_INTENT_KEYWORDS_EN = (
    "pain", "symptom", "medication", "dose", "diagnosis", "doctor", "allergy",
    "blood pressure", "surgery", "treatment", "lab test", "condition",
)
