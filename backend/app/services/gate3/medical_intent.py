"""Detect medical/care intents in chat messages (FA / AR / EN keyword lists)."""

import re
from functools import lru_cache

from backend.app.services.gate3.constants import (
    MEDICAL_INTENT_KEYWORDS_AR,
    MEDICAL_INTENT_KEYWORDS_EN,
    MEDICAL_INTENT_KEYWORDS_FA,
    MENTAL_WELLBEING_KEYWORDS_AR,
    MENTAL_WELLBEING_KEYWORDS_EN,
    MENTAL_WELLBEING_KEYWORDS_FA,
    keywords_for_language,
)


@lru_cache(maxsize=512)
def _latin_word_pattern(keyword: str) -> re.Pattern:
    # Short abbreviations ("ms", "als") must be whole words ("also" is not ALS);
    # longer terms match at a word start so inflections still count ("stressed", "diets").
    tail = r"(?![a-z0-9])" if len(keyword) <= 3 else ""
    return re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}{tail}")


def _contains_keyword(message: str, keywords: tuple) -> bool:
    raw = message or ""
    text = raw.strip().lower()
    if not text:
        return False
    for keyword in keywords:
        if keyword.isascii():
            # Whole words only, so "als" does not fire inside "also".
            if _latin_word_pattern(keyword).search(text):
                return True
        elif keyword in text or keyword in raw:
            return True
    return False


def is_medical_care_intent(message: str, language: str = "fa") -> bool:
    medical = keywords_for_language(
        language, fa=MEDICAL_INTENT_KEYWORDS_FA, ar=MEDICAL_INTENT_KEYWORDS_AR, en=MEDICAL_INTENT_KEYWORDS_EN
    )
    if _contains_keyword(message, medical):
        return True
    return is_mental_wellbeing_intent(message, language)


def is_mental_wellbeing_intent(message: str, language: str = "fa") -> bool:
    wellbeing = keywords_for_language(
        language,
        fa=MENTAL_WELLBEING_KEYWORDS_FA,
        ar=MENTAL_WELLBEING_KEYWORDS_AR,
        en=MENTAL_WELLBEING_KEYWORDS_EN,
    )
    return _contains_keyword(message, wellbeing)
