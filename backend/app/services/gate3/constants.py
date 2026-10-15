"""Gate 3 shared constants."""

PROVIDER_CATEGORIES = frozenset({
    "provider_directory", "lab_directory", "local_services", "culture", "sports", "science",
})

# Categories that must always require human review; auto-approve is never allowed.
SENSITIVE_REVIEW_REQUIRED_CATEGORIES = frozenset({
    "medical_condition", "medication_education", "clinical_guideline", "health_care",
    "caregiving", "chronic_care", "elderly_care", "emergency_education", "prevention",
    "diet_program", "exercise_program", "mental_wellbeing", "psychological_support",
    "emotional_support", "stress_management", "provider_directory", "lab_directory",
    "local_services",
})

# Low-risk categories that may allow auto_approve_low_risk when explicitly configured + high AI score.
LOW_RISK_AUTO_APPROVE_ELIGIBLE_CATEGORIES = frozenset({
    "culture", "sports", "science", "lifestyle", "beauty_wellness", "daily_planning",
    "habit_change", "other",
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
    # Conditions covered by governed I5 knowledge (D-010)
    "دیابت", "قند خون", "ام اس", "ای ال اس", "پارکینسون", "آلزایمر", "زوال عقل",
    "صرع", "تشنج", "سکته", "میگرن", "سرطان", "کلسترول", "کمردرد", "پوکی استخوان",
    "بی خوابی", "بی‌خوابی", "خستگی", "چاقی",
    # Healthy lifestyle: nutrition and physical activity
    "تغذیه", "رژیم", "ورزش", "وزن", "ویتامین", "فعالیت بدنی",
)
MEDICAL_INTENT_KEYWORDS_EN = (
    "pain", "symptom", "medication", "dose", "diagnosis", "doctor", "allergy",
    "blood pressure", "surgery", "treatment", "lab test", "condition",
    "diabetes", "blood sugar", "multiple sclerosis", "ms", "als", "motor neurone",
    "parkinson", "alzheimer", "dementia", "epilepsy", "seizure", "stroke", "migraine",
    "cancer", "cholesterol", "back pain", "osteoporosis", "insomnia", "fatigue", "obesity",
    "nutrition", "diet", "exercise", "workout", "physical activity", "weight", "vitamin",
)
MEDICAL_INTENT_KEYWORDS_AR = (
    "ألم", "أعراض", "عرض", "دواء", "جرعة", "مرض", "ضغط الدم", "قلب",
    "تحليل", "فحص", "جراحة", "طبيب", "حساسية", "تشخيص", "علاج",
    "السكري", "سكر الدم", "التصلب", "باركنسون", "الزهايمر", "الخرف", "الصرع",
    "السكتة", "الصداع", "سرطان", "الكوليسترول", "ألم الظهر", "هشاشة العظام",
    "الأرق", "التعب", "السمنة",
    "تغذية", "نظام غذائي", "رياضة", "تمارين", "الوزن", "فيتامين", "النشاط البدني",
)

MENTAL_WELLBEING_KEYWORDS_FA = (
    "استرس", "اضطراب", "افسردگی", "خواب", "تنهایی", "سوگ", "انگیزه", "عادت",
    "فرسودگی", "روان", "احساس", "حمایت عاطفی", "فشار روانی",
    "نگرانی", "ذهن آگاهی", "مدیتیشن", "آرامش",
)
MENTAL_WELLBEING_KEYWORDS_EN = (
    "stress", "anxiety", "sleep", "lonely", "loneliness", "grief", "motivation",
    "habit", "burnout", "emotional support", "mental wellbeing", "self-reflection",
    "worry", "mindfulness", "meditation", "low mood", "relax",
)
MENTAL_WELLBEING_KEYWORDS_AR = (
    "توتر", "قلق", "اكتئاب", "نوم", "وحدة", "حزن", "تحفيز", "عادة",
    "إرهاق", "نفسي", "مشاعر", "دعم عاطفي", "الصحة النفسية", "اليقظة الذهنية", "التأمل",
)


def keywords_for_language(language: str, *, fa: tuple, ar: tuple, en: tuple) -> tuple:
    """Language list plus EN (users often mix English terms such as "MS" or "ALS")."""
    lang = (language or "fa").lower()
    if lang.startswith("fa"):
        return fa + en
    if lang.startswith("ar"):
        return ar + en
    return en

PSYCHIATRIC_DISORDER_TERMS = (
    "depression disorder", "adhd", "bipolar disorder", "personality disorder",
    "anxiety disorder", "شما افسرده", "شما اضطراب", "بیماری دو قطبی",
)
