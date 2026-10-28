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


# R-033 (Javad 2026-10-28): Sedi must not put herself on trial in front of the user - no "I am not a psychologist", "I cannot
# diagnose", "I am only an AI". These patterns (checked on normalised text) mark such a clause; the guard removes the
# clause and keeps the useful rest of the sentence.
_SELF_LIMIT = re.compile(
    r"(?:"
    r"(?:روان ?شناس|پزشک|دکتر|متخصص|مشاور|درمانگر)(?: انسانی| واقعی| حرفه ای)? نیستم|"
    r"(?:نمی ?تونم|نمیتونم|نمی ?توانم|نمیتوانم)(?: که)? (?:بیماری |اختلال )?تشخیص|"
    r"تشخیص (?:نمی ?دم|نمیدم|نمی ?دهم|نمیدهم)|"
    r"توانایی (?:تشخیص|درمان) ندارم|"
    r"فقط (?:یه|یک) (?:هوش مصنوعی|برنامه|دستیار)|"
    r"جایگزین (?:پزشک|روان ?شناس|متخصص)(?: نیستم| نمی ?شم| نمی ?شوم)|"
    r"\bi(?:'m| am) not (?:a |an )?(?:human )?(?:psychologist|therapist|doctor|physician|counsel+or)\b|"
    r"\bi (?:cannot|can't|can not|don't|do not) (?:really )?diagnos|"
    r"\bi(?:'m| am) (?:just|only|merely) an? (?:ai|assistant|program|bot)\b|"
    r"\bas an ai\b|"
    r"لست (?:أخصائية|اخصائية|طبيبة|معالجة|مختصة)|"
    r"لا أستطيع (?:ال)?تشخيص|لا أشخّص|لا اشخص|"
    r"(?:أنا )?مجرد (?:ذكاء اصطناعي|برنامج)"
    r")",
    re.I,
)
_CLAUSE_SPLIT = re.compile(r"\s*[؛;]\s*|\s+(?:اما|ولی|ولي|but|لكن|لكنني)\s+", re.I)
_END_PUNCT = ".!?؟!…"


def strip_self_limit_disclaimers(reply: str, language: str = "fa") -> str:
    """R-033: drop the clauses where Sedi talks about her own limits; keep the helpful rest verbatim. Never empties a reply."""
    text = (reply or "").strip()
    if not text:
        return text
    sep = "; " if (language or "fa").split("-")[0].lower() == "en" else "؛ "
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    out: list[str] = []
    changed = False
    for p in parts:
        if not _SELF_LIMIT.search(_norm(p)):
            out.append(p.strip())
            continue
        changed = True
        clauses = [c.strip() for c in _CLAUSE_SPLIT.split(p) if c and c.strip()]
        kept = [c for c in clauses if not _SELF_LIMIT.search(_norm(c))]
        if kept:
            s = sep.join(kept)
            tail = p.rstrip()[-1:] if p.rstrip() else ""
            if tail in _END_PUNCT and not s.endswith(tuple(_END_PUNCT)):
                s += tail
            out.append(s)
    if not changed or not out:
        return text
    return " ".join(out)


def limit_questions(reply: str, max_questions: int = 1) -> str:
    """R-020: Sedi talks like a friend, not an interviewer — keep at most ``max_questions`` question sentences
    (the first ones); every statement is kept. Deterministic, never empties a reply."""
    text = (reply or "").strip()
    if not text:
        return text
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    kept: list[str] = []
    asked = 0
    for p in parts:
        is_q = p.rstrip().endswith(("؟", "?"))
        if is_q:
            asked += 1
            if asked > max_questions:
                continue
        kept.append(p.strip())
    if not kept or len(kept) == len(parts):
        return text
    return " ".join(kept)
