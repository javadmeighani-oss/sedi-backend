# backend.app.services.knowledge.stated_facts_extractor_v1
"""R-014 "second memory": deterministic extraction of facts the USER explicitly states about themselves.

Rule-based, no LLM, no inference: a fact is produced only from a first-person statement ("دیابت دارم", "مادرم سرطان
داشت", "I have asthma"). Questions ("آیا دیابت دارم؟"), negations ("دیابت ندارم") and conditionals never match;
hedged statements ("فکر کنم دیابت دارم") get a lower confidence so they stay candidates (not auto-accepted).
Output is fed to the existing KC pipeline -> I6 ``write_fact`` (consent-gated) by ``conversation_extractor_v1``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# (label, regex) — label is what is remembered. Persian first, then English.
_CONDITIONS_FA = (
    ("دیابت", r"دیابت(?:\s*نوع\s*[12])?|قند\s*خون|دیابتی"),
    ("فشار خون بالا", r"فشار\s*خون(?:\s*بالا)?|فشارخون(?:\s*بالا)?"),
    ("فشار خون پایین", r"فشار\s*خون\s*پایین|فشارخون\s*پایین"),
    ("کلسترول بالا", r"کلسترول(?:\s*بالا)?"),
    ("چربی خون", r"چربی\s*خون"),
    ("تیروئید", r"تیروئید|تیروید"),
    ("آسم", r"آسم"),
    ("میگرن", r"میگرن"),
    ("آرتروز", r"آرتروز"),
    ("سرطان", r"سرطان"),
    ("ام‌اس", r"ام[‌ ]?اس"),
    ("ای‌ال‌اس", r"ای[‌ ]?ال[‌ ]?اس|\bALS\b"),
    ("افسردگی", r"افسردگی"),
    ("اضطراب", r"اضطراب"),
    ("کم‌خونی", r"کم[‌ ]?خونی"),
    ("نقرس", r"نقرس"),
    ("کبد چرب", r"کبد\s*چرب"),
    ("سنگ کلیه", r"سنگ\s*کلیه"),
    ("ریفلاکس", r"ریفلاکس|رفلاکس"),
    ("آلزایمر", r"آلزایمر"),
    ("پارکینسون", r"پارکینسون"),
    ("صرع", r"صرع"),
    ("بیماری قلبی", r"بیماری\s*قلبی|مشکل\s*قلبی|ناراحتی\s*قلبی"),
    ("بی‌خوابی", r"بی[‌ ]?خوابی"),
    ("اضافه وزن", r"اضافه[‌ ]?وزن|چاقی"),
)
_CONDITIONS_EN = (
    ("diabetes", r"diabetes|diabetic"),
    ("hypertension", r"hypertension|high\s+blood\s+pressure"),
    ("high cholesterol", r"high\s+cholesterol"),
    ("asthma", r"asthma"),
    ("migraine", r"migraines?"),
    ("arthritis", r"arthritis"),
    ("cancer", r"cancer"),
    ("multiple sclerosis", r"multiple\s+sclerosis|\bMS\b"),
    ("ALS", r"\bALS\b"),
    ("depression", r"depression"),
    ("anxiety", r"anxiety"),
    ("anemia", r"anemia|anaemia"),
    ("thyroid disease", r"thyroid\s+(?:disease|problem|issue)s?"),
    ("heart disease", r"heart\s+(?:disease|problem|condition)"),
    ("epilepsy", r"epilepsy"),
)

_RELATIVES_FA = {
    "مادرم": "مادر", "مادر من": "مادر", "پدرم": "پدر", "پدر من": "پدر", "خواهرم": "خواهر", "برادرم": "برادر",
    "مادربزرگم": "مادربزرگ", "پدربزرگم": "پدربزرگ", "همسرم": "همسر", "فرزندم": "فرزند",
}
_RELATIVES_EN = {
    "my mother": "mother", "my mom": "mother", "my father": "father", "my dad": "father", "my sister": "sister",
    "my brother": "brother", "my grandmother": "grandmother", "my grandfather": "grandfather",
}

_HEDGE = re.compile(r"(?:فکر\s*کنم|فکر\s*می[‌ ]?کنم|شاید|احتمالا|احتمالاً|ظاهرا|ظاهراً|i\s+think|maybe|probably)", re.I)
_QUESTION = re.compile(r"(?:[؟?]|^\s*آیا\b|^\s*(?:do|am|is|can)\b)", re.I)
_CONDITIONAL = re.compile(r"(?:اگه|اگر|if)\b", re.I)
_SENTENCE_SPLIT = re.compile(r"[.!؟?\n]+")

_SELF_VERB_FA = r"(?:دارم|داشتم|گرفتم)"
_REL_VERB_FA = r"(?:داره|دارد|داشت|داشته|دارن|دارند|داشتند|گرفته|گرفت)"

_JOBS_FA = (
    "معلم", "پرستار", "راننده", "دانشجو", "کارمند", "بازنشسته", "خانه‌دار", "خانه دار", "پزشک", "مهندس",
    "برنامه‌نویس", "برنامه نویس", "کارگر", "کشاورز", "فروشنده", "حسابدار", "وکیل", "استاد", "دانش‌آموز", "دانش آموز",
    "طراح", "نقاش", "آشپز", "ورزشکار", "مربی", "داروساز", "دندانپزشک", "معمار", "خبرنگار", "نویسنده", "مدیر",
)
_JOBS_EN = (
    "teacher", "nurse", "driver", "student", "engineer", "developer", "programmer", "accountant", "lawyer",
    "designer", "doctor", "manager", "retired", "farmer", "cook", "writer", "artist",
)


@dataclass(frozen=True)
class Stated:
    fact_key: str
    fact_value: object
    confidence: float
    pattern_id: str


def _conf(sentence: str, base: float = 0.88) -> float:
    return 0.7 if _HEDGE.search(sentence) else base


def _condition_label(label: str, matched: str) -> str:
    if label == "فشار خون بالا" and "پایین" in matched:
        return "فشار خون پایین"
    return label


def _find_condition(chunk: str, lex) -> Optional[str]:
    for label, rx in lex:
        m = re.search(rf"(?:{rx})", chunk, re.I)
        if m:
            return _condition_label(label, m.group(0))
    return None


def _own_conditions(sentence: str) -> List[Stated]:
    out: List[Stated] = []
    for label, rx in _CONDITIONS_FA:
        pats = (
            rf"(?:{rx})(?:\s*(?:بالا|پایین))?(?:\s+هم)?\s+{_SELF_VERB_FA}\b",
            rf"مبتلا\s+به\s+(?:بیماری\s+)?(?:{rx})",
            rf"(?:{rx})\s*(?:م|ام)\s+(?:بالاست|پایینه|بالاس|زیاده|بالاتره)",
            rf"(?:{rx})ی\s+(?:هستم|ام)\b" if label == "دیابت" else None,
        )
        for p in pats:
            if p and (m := re.search(p, sentence, re.I)):
                out.append(Stated("health_concerns", _condition_label(label, m.group(0)), _conf(sentence), "stated_condition_fa"))
                break
    for label, rx in _CONDITIONS_EN:
        if re.search(rf"\bi\s+(?:have|suffer\s+from|was\s+diagnosed\s+with|got)\s+(?:type\s*[12]\s+)?(?:{rx})", sentence, re.I):
            out.append(Stated("health_concerns", label, _conf(sentence), "stated_condition_en"))
    return out


def _family_conditions(sentence: str) -> List[Stated]:
    out: List[Stated] = []
    for rel_raw, rel in _RELATIVES_FA.items():
        if rel_raw in sentence:
            chunk = sentence.split(rel_raw, 1)[1]
            if re.search(_REL_VERB_FA, chunk):
                label = _find_condition(chunk, _CONDITIONS_FA)
                if label and re.search(rf"(?:{'|'.join(r for _l, r in _CONDITIONS_FA)})\s*(?:بالا|پایین)?\s*{_REL_VERB_FA}", chunk):
                    out.append(Stated("family_history", f"{rel}: {label}", _conf(sentence), "stated_family_fa"))
    low = sentence.lower()
    for rel_raw, rel in _RELATIVES_EN.items():
        if rel_raw in low:
            chunk = low.split(rel_raw, 1)[1]
            if re.search(r"\b(?:has|had|have|suffers?|died\s+of)\b", chunk):
                label = _find_condition(chunk, _CONDITIONS_EN)
                if label:
                    out.append(Stated("family_history", f"{rel}: {label}", _conf(sentence), "stated_family_en"))
    return out


def _occupation(sentence: str) -> List[Stated]:
    out: List[Stated] = []
    m = re.search(r"شغلم\s+(\S+(?:\s+\S+)?)", sentence)
    if m:
        val = re.sub(r"\s*(?:است|هست|ـه)$", "", m.group(1).strip())
        if 2 <= len(val) <= 30:
            out.append(Stated("occupation_stated", val, _conf(sentence), "stated_job_fa1"))
    for job in _JOBS_FA:
        if re.search(rf"(?:^|\s){re.escape(job)}(?:م|\s*هستم|\s*ام)(?:\s|$)", sentence):
            out.append(Stated("occupation_stated", job, _conf(sentence), "stated_job_fa2"))
            break
    m = re.search(r"به\s+عنوان\s+(\S+(?:\s+\S+)?)\s+کار\s+می[‌ ]?کنم", sentence)
    if m:
        out.append(Stated("occupation_stated", m.group(1).strip(), _conf(sentence), "stated_job_fa3"))
    for job in _JOBS_EN:
        if re.search(rf"\bi(?:'m|\s+am)\s+an?\s+{job}\b|\bi\s+work\s+as\s+an?\s+{job}\b", sentence, re.I):
            out.append(Stated("occupation_stated", job, _conf(sentence), "stated_job_en"))
            break
    return out


def _household(sentence: str) -> List[Stated]:
    if re.search(r"تنها\s+زندگی\s+می[‌ ]?کنم|\bi\s+live\s+alone\b", sentence, re.I):
        return [Stated("household_context", "lives alone" if sentence.isascii() else "تنها زندگی می‌کند", _conf(sentence), "stated_household_alone")]
    m = re.search(r"با\s+(همسرم|خانواده|خانواده‌ام|مادرم|پدرم|فرزندم|فرزندانم|بچه‌هام|والدینم)\s+زندگی\s+می[‌ ]?کنم", sentence)
    if m:
        return [Stated("household_context", f"با {m.group(1)} زندگی می‌کند", _conf(sentence), "stated_household_with")]
    return []


def _interests(sentence: str) -> List[Stated]:
    out: List[Stated] = []
    for m in re.finditer(r"به\s+(.{2,30}?)\s+(?:خیلی\s+)?علاقه\s*(?:دارم|مندم)", sentence):
        val = m.group(1).strip(" ،")
        if val and not re.search(r"\b(?:این|اون|آن)\b", val):
            out.append(Stated("interests", val, _conf(sentence), "stated_interest_fa"))
    for m in re.finditer(r"عاشق\s+(.{2,25}?)\s*(?:هستم|ام)\b", sentence):
        out.append(Stated("interests", m.group(1).strip(" ،"), _conf(sentence), "stated_interest_fa2"))
    return out


def _sleep_hours(sentence: str) -> List[Stated]:
    m = re.search(r"(\d{1,2})\s*ساعت\s+(?:در\s+شب\s+|شبی\s+)?(?:می[‌ ]?خوابم|خواب\s+دارم)", sentence)
    if m:
        h = int(m.group(1))
        if 1 <= h <= 14:
            return [Stated("sleep_duration_hours", h, _conf(sentence), "stated_sleep_hours")]
    return []


def extract_stated_facts(text: str) -> List[Stated]:
    """All explicit first-person facts in ``text`` (digits normalised); may contain duplicates (caller dedupes)."""
    if not text or not isinstance(text, str):
        return []
    norm = text.translate(_DIGITS)
    out: List[Stated] = []
    for sentence in _SENTENCE_SPLIT.split(norm):
        s = sentence.strip()
        if len(s) < 4 or _QUESTION.search(s) or _CONDITIONAL.search(s):
            continue
        out.extend(_family_conditions(s))
        out.extend(_own_conditions(s))
        out.extend(_occupation(s))
        out.extend(_household(s))
        out.extend(_interests(s))
        out.extend(_sleep_hours(s))
    return out
