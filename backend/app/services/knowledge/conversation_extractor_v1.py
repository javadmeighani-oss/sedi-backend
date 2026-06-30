# app/services/knowledge/conversation_extractor_v1.py
"""Conversation Extraction V1: rule-based, deterministic extraction from chat text. No LLM."""
import json
import os
import re
import string
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# Lightweight normalization + noise filter for extraction QA (stopwords/noise not stored as candidates).
_STOPWORDS_FA = frozenset({
    "هم", "و", "یا", "که", "در", "به", "از", "با", "برای", "این", "اون", "آن",
    "من", "تو", "ما", "شما", "او", "اگه", "اگر", "نه", "بله",
})
_STOPWORDS_EN = frozenset({
    "and", "or", "the", "a", "an", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "i", "you", "we", "they", "he", "she", "it", "yes", "no",
})
_STOPWORDS_AR = frozenset({
    "و", "أو", "او", "في", "على", "من", "إلى", "الي", "عن", "مع",
    "هذا", "هذه", "ذلك", "تلك", "أنا", "انت", "أنت", "نحن", "هو", "هي", "نعم", "لا", "ليس",
})

# Unicode normalization: Arabic Yeh/Kaf -> Persian, remove diacritics/tatweel (for matching and stopwords).
# Ranges removed: [\u064B-\u0652] (harakat), \u0670 (dagger alif), \u0640 (tatweel). ZWNJ \u200c kept.
def _unicode_normalize_pass(s: str) -> str:
    """Arabic yeh/kaf -> Persian; remove tatweel and Arabic diacritics. Safe for tokens."""
    if not s:
        return s
    t = s.replace("\u064A", "\u06CC")  # Arabic yeh ي -> Persian ی
    t = t.replace("\u0643", "\u06A9")  # Arabic kaf ك -> Persian ک
    t = t.replace("\u0640", "")        # tatweel/kashida ـ
    t = re.sub(r"[\u064B-\u0652]", "", t)  # Arabic diacritics (FATHATAN through SUKUN)
    t = t.replace("\u0670", "")        # dagger alif
    return t


_STOPWORDS = _STOPWORDS_FA | _STOPWORDS_EN | frozenset(_unicode_normalize_pass(w) for w in _STOPWORDS_AR)
_PUNCT = frozenset(string.punctuation + "،؛؟\u200c")


def _normalize_token(s: str) -> str:
    """Strip, lower, collapse internal whitespace, unicode normalize (yeh/kaf, diacritics, tatweel), remove surrounding punctuation. ZWNJ preserved."""
    if not s or not isinstance(s, str):
        return ""
    t = s.strip().lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = _unicode_normalize_pass(t)
    while t and t[0] in _PUNCT:
        t = t[1:]
    while t and t[-1] in _PUNCT:
        t = t[:-1]
    return t


def _is_noise_or_stopword(s: str) -> bool:
    """Reject if token is too short, numeric-only, punctuation-only, or in stopwords (after normalize)."""
    norm = _normalize_token(s)
    if len(norm) < 2:
        return True
    if norm.isdigit():
        return True
    if all(c in _PUNCT or c.isspace() for c in norm):
        return True
    if norm in _STOPWORDS:
        return True
    return False


@dataclass
class ExtractedCandidate:
    fact_key: str
    fact_value: Any
    confidence: float
    evidence: str
    pattern_id: str


def _get_max_extracted() -> int:
    return int(os.environ.get("KC_MAX_EXTRACTED_PER_MESSAGE", "3"))


def _dedupe_and_cap(candidates: List[ExtractedCandidate], cap: int) -> List[ExtractedCandidate]:
    """Dedupe by (fact_key, str(fact_value)), keep max confidence. Cap by KC_MAX_EXTRACTED_PER_MESSAGE."""
    seen: Dict[Tuple[str, str], ExtractedCandidate] = {}
    for c in candidates:
        key = (c.fact_key, json.dumps(c.fact_value, ensure_ascii=False, default=str))
        if key not in seen or c.confidence > seen[key].confidence:
            seen[key] = c
    sorted_vals = sorted(seen.values(), key=lambda x: -x.confidence)
    return sorted_vals[:cap]


def extract_candidates(text: str, language: str) -> List[ExtractedCandidate]:
    """Extract fact candidates from user chat text. Deterministic, stdlib only."""
    if not text or not isinstance(text, str):
        return []
    text = text.strip()
    if not text:
        return []

    candidates: List[ExtractedCandidate] = []

    # 1) sleep_quality
    if re.search(r"خوابم\s*(بد|خوب\s*نبود|افتضاح)", text, re.I):
        candidates.append(ExtractedCandidate(
            fact_key="sleep_quality",
            fact_value="poor",
            confidence=0.85,
            evidence=text[:200],
            pattern_id="sleep_quality_poor_fa",
        ))
    if re.search(r"خوابم\s*(خوب|عالی)\s*(بود)?", text, re.I):
        candidates.append(ExtractedCandidate(
            fact_key="sleep_quality",
            fact_value="good",
            confidence=0.85,
            evidence=text[:200],
            pattern_id="sleep_quality_good_fa",
        ))

    # 2) stress_level
    if re.search(r"(استرس\s*دارم|خیلی\s*استرس|استرس\s*زیاد)", text, re.I):
        candidates.append(ExtractedCandidate(
            fact_key="stress_level",
            fact_value="high",
            confidence=0.80,
            evidence=text[:200],
            pattern_id="stress_high_fa",
        ))
    if re.search(r"(استرس\s*ندارم|آرومم|آرامم)", text, re.I):
        candidates.append(ExtractedCandidate(
            fact_key="stress_level",
            fact_value="low",
            confidence=0.75,
            evidence=text[:200],
            pattern_id="stress_low_fa",
        ))

    # 3) daily_walk_minutes
    if re.search(r"روزانه\s*نیم\s*ساعت\s*پیاده", text, re.I):
        candidates.append(ExtractedCandidate(
            fact_key="daily_walk_minutes",
            fact_value=30,
            confidence=0.85,
            evidence=text[:200],
            pattern_id="daily_walk_half_hour_fa",
        ))
    m = re.search(r"(\d+)\s*دقیقه\s*پیاده", text)
    if m:
        try:
            mins = int(m.group(1))
            if 1 <= mins <= 180:
                candidates.append(ExtractedCandidate(
                    fact_key="daily_walk_minutes",
                    fact_value=mins,
                    confidence=0.80,
                    evidence=text[:200],
                    pattern_id="daily_walk_minutes_fa",
                ))
        except (ValueError, TypeError):
            pass

    # 4) medications
    # Persian present: "دارم (X) می‌خورم" / "قرص (X)" / "(X) مصرف می‌کنم"
    # Persian past: "(X) خوردم", "(X) مصرف کردم" / "مصرف‌کردم" (ZWNJ)
    med_patterns = [
        r"دارم\s+([^\s،.]+?)\s+می[‌\s]*خورم",
        r"قرص\s+([^\s،.]+?)(?:\s+می[‌\s]*خورم|\s*$|[\s،.])",
        r"([^\s،.]+?)\s+مصرف\s+می[‌\s]*کنم",
        r"([^\s،.]+?)\s+خوردم",
        r"([^\s،.]+?)\s+مصرف[\s\u200c]*کردم",
    ]
    has_mg = bool(re.search(r"mg|میلی[‌\s]*گرم|ملی[‌\s]*گرم", text, re.I))
    for pat in med_patterns:
        for m in re.finditer(pat, text, re.I):
            token = (m.group(1) or "").strip()
            token = re.sub(r"[,،.\s]+", " ", token).strip()
            if len(token) >= 2 and not _is_noise_or_stopword(token):
                conf = 0.80 if has_mg else 0.70
                candidates.append(ExtractedCandidate(
                    fact_key="medications",
                    fact_value=token,
                    confidence=conf,
                    evidence=text[:200],
                    pattern_id="medications_fa",
                ))

    # Arabic medications: when language is ar or text contains Arabic letters
    _has_arabic = language == "ar" or bool(re.search(r"[\u0600-\u06FF]", text))
    if _has_arabic:
        text_ar = _unicode_normalize_pass(text)  # so triggers with diacritics (e.g. أَتناول) match
        ar_med_patterns = [
            r"أتناول\s+([^\s،.]+)",
            r"تناولت\s+([^\s،.]+)",
            r"آخذ\s+([^\s،.]+)",
            r"أخذت\s+([^\s،.]+)",
            r"أخذت\s+([^\s،.]+)",  # alternate hamza
            r"دواء\s+([^\s،.]+)",
            r"حبوب\s+([^\s،.]+)",
            r"قرص\s+([^\s،.]+)",
        ]
        for pat in ar_med_patterns:
            for m in re.finditer(pat, text_ar):
                token = (m.group(1) or "").strip()
                token = re.sub(r"[,،.\s]+", " ", token).strip()
                if len(token) >= 2 and not _is_noise_or_stopword(token):
                    conf = 0.80 if has_mg else 0.70
                    candidates.append(ExtractedCandidate(
                        fact_key="medications",
                        fact_value=token,
                        confidence=conf,
                        evidence=text[:200],
                        pattern_id="medications_ar",
                    ))

    # Drop any candidate whose string value normalizes to noise/stopword
    candidates = [
        c for c in candidates
        if not (isinstance(c.fact_value, str) and _is_noise_or_stopword(c.fact_value))
    ]

    # 5) Gate 2: Persian time-bound events → user_events (via user_event candidate + promotion)
    candidates.extend(_extract_persian_event_candidates(text))

    return _dedupe_and_cap(candidates, _get_max_extracted())


def _relative_starts_at(day_hint: str) -> str:
    """Approximate ISO datetime for promotion (UTC, date-only semantics)."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    hint = (day_hint or "").strip()
    if hint in ("فردا", "tomorrow"):
        return (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0).isoformat()
    if hint in ("جمعه",):
        return (now + timedelta(days=(4 - now.weekday()) % 7 or 7)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    if "هفته" in hint and "بعد" in hint:
        return (now + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    if "ماه" in hint and "بعد" in hint:
        return (now + timedelta(days=30)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    if "سه" in hint and "شنبه" in hint:
        return (now + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    return (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


def _extract_persian_event_candidates(text: str) -> List[ExtractedCandidate]:
    """Minimal Persian patterns for scheduled/important events (Gate 2)."""
    out: List[ExtractedCandidate] = []
    patterns = [
        (r"فردا\s*ساعت\s*(\d{1,2})", "work", "work_meeting", "جلسه کاری", "فردا", 0.84, "event_work_meeting_fa"),
        (r"جلسه\s*کاری", "work", "work_meeting", "جلسه کاری", "فردا", 0.80, "event_work_meeting_fa2"),
        (r"امتحان\s*دارم", "education", "exam", "امتحان", "جمعه", 0.82, "event_exam_fa"),
        (r"تولد\s*.+", "family", "birthday", "تولد", "هفته بعد", 0.78, "event_birthday_fa"),
        (r"آزمایش\s*خون", "medical", "lab_test", "آزمایش خون", "سه‌شنبه", 0.86, "event_lab_test_fa"),
        (r"جراحی\s*دارم", "medical", "surgery", "جراحی", "ماه بعد", 0.84, "event_surgery_fa"),
        (r"نوبت\s*دکتر", "medical", "doctor_visit", "نوبت دکتر", "آینده", 0.85, "event_doctor_visit_fa"),
    ]
    for pat, domain, etype, title, day_hint, conf, pid in patterns:
        if re.search(pat, text, re.I):
            hour = None
            hm = re.search(r"ساعت\s*(\d{1,2})", text)
            if hm:
                try:
                    hour = int(hm.group(1))
                except ValueError:
                    hour = None
            starts = _relative_starts_at(day_hint)
            if hour is not None:
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(starts)
                    starts = dt.replace(hour=min(hour, 23)).isoformat()
                except ValueError:
                    pass
            out.append(ExtractedCandidate(
                fact_key="user_event",
                fact_value={
                    "title": title,
                    "event_domain": domain,
                    "event_type": etype,
                    "starts_at": starts,
                },
                confidence=conf,
                evidence=text[:200],
                pattern_id=pid,
            ))
    return out
