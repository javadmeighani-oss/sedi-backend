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
_STOPWORDS = _STOPWORDS_FA | _STOPWORDS_EN
_PUNCT = frozenset(string.punctuation + "،؛؟\u200c")


def _normalize_token(s: str) -> str:
    """Strip, lower, collapse internal whitespace, remove surrounding punctuation."""
    if not s or not isinstance(s, str):
        return ""
    t = s.strip().lower()
    t = re.sub(r"\s+", " ", t).strip()
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
    # "دارم (X) می‌خورم" / "قرص (X)" / "(X) مصرف می‌کنم"
    med_patterns = [
        r"دارم\s+([^\s،.]+?)\s+می[‌\s]*خورم",
        r"قرص\s+([^\s،.]+?)(?:\s+می[‌\s]*خورم|\s*$|[\s،.])",
        r"([^\s،.]+?)\s+مصرف\s+می[‌\s]*کنم",
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

    # Drop any candidate whose string value normalizes to noise/stopword
    candidates = [
        c for c in candidates
        if not (isinstance(c.fact_value, str) and _is_noise_or_stopword(c.fact_value))
    ]
    return _dedupe_and_cap(candidates, _get_max_extracted())
