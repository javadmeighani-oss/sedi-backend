# backend.app.services.intelligence.grounding_guard
"""R-014 (2026-10-24): Sedi must never state a personal or family health fact that was not recorded or said.

A pure, deterministic post-generation filter (no I/O, no LLM). It removes a sentence of the model's reply when that
sentence asserts a relative's condition ("با توجه به اینکه مادرت دیابت داشته…") and either the relative or the
condition never appears in what the user said / what the user's memory supplied. First-person claims by Sedi about her
own relatives ("مادرم دیابت داره") are always removed — Sedi is an AI companion and has no such family history.
"""
from __future__ import annotations

import re
from typing import Iterable

_RELATIVE_TERMS = (
    "مادر", "پدر", "خواهر", "برادر", "همسر", "فرزند", "دختر", "پسر", "پدربزرگ", "مادربزرگ", "عمو", "عمه", "دایی",
    "خاله", "نوه", "خانواده", "والدین",
    "mother", "father", "sister", "brother", "wife", "husband", "parent", "grandmother", "grandfather", "family",
    "أم", "أب", "اخت", "أخت", "أخ", "زوج", "عائل",
)
_CONDITION_TERMS = (
    "دیابت", "قند", "فشار خون", "فشارخون", "سرطان", "قلب", "سکته", "کلسترول", "چاقی", "آلزایمر", "ام اس", "کلیه",
    "آسم", "صرع", "افسردگی", "بیماری",
    "diabet", "cancer", "hypertension", "blood pressure", "heart", "stroke", "cholesterol", "obesity", "alzheimer",
    "kidney", "asthma", "epilep", "depress", "illness", "disease",
    "سكري", "سرطان", "ضغط", "قلب", "مرض",
)
_CLAIM_VERB = re.compile(
    r"(?:داشت|داره|دارد|دارند|داشته|مبتلا|گرفته|گرفت|بوده|سابقه|had|has|have|suffer|diagnosed|history|كان|لديه|عانى)",
    re.I,
)
_FIRST_PERSON_RELATIVE = re.compile(
    r"(?:مادرم|پدرم|خواهرم|برادرم|همسرم|مادر\s+من|پدر\s+من|\bmy\s+(?:mother|father|sister|brother|mom|dad)\b|أمي|أبي)",
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟!\n])\s+|\n+")

_FALLBACK = {
    "fa": "برای اینکه دقیق‌ترین پیشنهاد رو بهت بدم، اول می‌خوام درباره‌ی وضعیت خودت بیشتر بدونم؛ برام تعریف کن.",
    "en": "To give you the most accurate suggestion, I'd like to know more about your own situation first. Tell me more.",
    "ar": "لأقدّم لك أدق اقتراح أودّ أن أعرف عن وضعك أكثر أولاً؛ حدّثني.",
}


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("‌", " ").split())


def _terms_in(text: str, terms: Iterable[str]) -> list[str]:
    return [t for t in terms if t in text]


def _is_unsupported(sentence: str, haystack: str) -> bool:
    s = _norm(sentence)
    if not _CLAIM_VERB.search(s):
        return False
    if _FIRST_PERSON_RELATIVE.search(s) and _terms_in(s, _CONDITION_TERMS):
        return True
    relatives = _terms_in(s, _RELATIVE_TERMS)
    conditions = _terms_in(s, _CONDITION_TERMS)
    if not relatives or not conditions:
        return False
    # The sentence ties a relative to a condition: both must be grounded in user-sourced text.
    if not any(r in haystack for r in relatives):
        return True
    return not any(c in haystack for c in conditions)


def strip_unsupported_personal_claims(reply: str, supported_text: str, language: str = "fa") -> str:
    """Drop sentences that assert unrecorded relative/condition facts; keep the rest verbatim."""
    text = (reply or "").strip()
    if not text:
        return text
    haystack = _norm(supported_text)
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    kept = [p for p in parts if not _is_unsupported(p, haystack)]
    if len(kept) == len(parts):
        return text
    if not kept:
        lang = (language or "fa").split("-")[0].lower()
        return _FALLBACK.get(lang, _FALLBACK["en"])
    return " ".join(k.strip() for k in kept)
