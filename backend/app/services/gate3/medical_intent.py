"""Detect medical/care intents in chat messages."""

from backend.app.services.gate3.constants import (
    MEDICAL_INTENT_KEYWORDS_EN,
    MEDICAL_INTENT_KEYWORDS_FA,
    MENTAL_WELLBEING_KEYWORDS_EN,
    MENTAL_WELLBEING_KEYWORDS_FA,
)


def is_medical_care_intent(message: str, language: str = "fa") -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    lang = (language or "fa").lower()
    keywords = MEDICAL_INTENT_KEYWORDS_FA if lang.startswith("fa") else MEDICAL_INTENT_KEYWORDS_EN
    if any(k in text or k in (message or "") for k in keywords):
        return True
    wb = MENTAL_WELLBEING_KEYWORDS_FA if lang.startswith("fa") else MENTAL_WELLBEING_KEYWORDS_EN
    return any(k in text or k in (message or "") for k in wb)


def is_mental_wellbeing_intent(message: str, language: str = "fa") -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    lang = (language or "fa").lower()
    wb = MENTAL_WELLBEING_KEYWORDS_FA if lang.startswith("fa") else MENTAL_WELLBEING_KEYWORDS_EN
    return any(k in text or k in (message or "") for k in wb)
