# backend.app.services.lifestyle.fact_extractor (Stage 17.1)
"""
Safe-by-default fact extraction from chat turns.
Deterministic patterns first; optional AI assist behind LIFESTYLE_AI_EXTRACT.
"""

import os
import re
import json
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

LIFESTYLE_AI_EXTRACT = os.environ.get("LIFESTYLE_AI_EXTRACT", "false").lower() in ("true", "1", "yes")

ALLOWED_DOMAINS_V1 = {"sleep", "activity", "medication", "mood"}

# UserMemoryFact domain for storage (routines has wake_time/bedtime)
def _fact_domain(domain: str, key: str) -> str:
    if domain == "sleep" and key in ("bedtime", "wake_time"):
        return "routines"
    if domain == "sleep":
        return "lifestyle"
    if domain == "activity":
        return "lifestyle"
    if domain == "medication":
        return "medical"
    if domain == "mood":
        return "lifestyle"
    return "lifestyle"


@dataclass
class CandidateFact:
    domain: str
    key: str
    value: any
    confidence: float
    is_explicit: bool
    fact_domain: str  # UserMemoryFact domain
    fact_key: str    # UserMemoryFact key


# Deterministic patterns: (regex, domain, key, is_explicit, confidence)
_SLEEP_PATTERNS = [
    (r"(?:I sleep|I slept|خوابم|خوابیدم|I get)\s+(?:about\s+)?(\d+(?:\.\d+)?)\s*(?:hours?|ساعت)", "sleep", "sleep_duration_hours", True, 0.9),
    (r"(?:I wake|بیدار می‌شوم|I get up)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)", "sleep", "wake_time", True, 0.85),
    (r"(?:I go to bed|می‌خوابم)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)", "sleep", "bedtime", True, 0.85),
    (r"(?:sleep quality|کیفیت خواب)\s*(?:is|was)?\s*(\w+)", "sleep", "sleep_quality", True, 0.8),
]

_ACTIVITY_PATTERNS = [
    (r"(?:I walked|I ran|walked|ran)\s+(?:about\s+)?(\d+)\s*(?:steps?|قدم)", "activity", "steps_count", True, 0.9),
    (r"(?:I exercised|تمرین کردم|exercise)\s+(?:for\s+)?(\d+)\s*(?:minutes?|دقیقه)", "activity", "exercise_minutes", True, 0.9),
    (r"(?:today I walked|امروز راه رفتم)\s+(\d+)", "activity", "steps_count", True, 0.9),
    (r"(\d+)\s*(?:steps?|قدم)\s+(?:today|امروز)", "activity", "steps_count", True, 0.85),
]

_MOOD_PATTERNS = [
    (r"(?:I feel|I'm feeling|حالم|احساس می‌کنم)\s+(good|great|fine|ok|happy|tired|stressed|خوب|خسته|خوشحال)", "mood", "mood", True, 0.85),
    (r"(?:my mood|حال و هوام)\s+(?:is\s+)?(\w+)", "mood", "mood", True, 0.85),
]

_MEDICATION_PATTERNS = [
    (r"(?:I take|می‌خورم|I took)\s+([^,.]+?)\s+(?:daily|every day|هر روز)", "medication", "medications", True, 0.9),
    (r"(?:take|taking)\s+(\w+)\s+(?:as prescribed|طبق دستور)", "medication", "medications", True, 0.9),
]


def extract_candidates_from_turn(
    user_id: int,
    user_message: str,
    assistant_message: str,
    language: str = "en",
) -> List[CandidateFact]:
    """
    Extract candidate facts from a chat turn. Deterministic first; optional AI assist.
    """
    candidates: List[CandidateFact] = []
    text = (user_message or "") + " " + (assistant_message or "")
    text_lower = text.lower().strip()
    if not text_lower:
        return candidates

    patterns = _SLEEP_PATTERNS + _ACTIVITY_PATTERNS + _MOOD_PATTERNS + _MEDICATION_PATTERNS
    for pat, domain, key, is_explicit, conf in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if not raw or len(raw) > 200:
                continue
            fact_domain = _fact_domain(domain, key)
            fact_key = key
            value = _normalize_value(key, raw)
            if value is None:
                continue
            candidates.append(CandidateFact(
                domain=domain,
                key=fact_key,
                value=value,
                confidence=conf,
                is_explicit=is_explicit,
                fact_domain=fact_domain,
                fact_key=fact_key,
            ))

    if LIFESTYLE_AI_EXTRACT and len(candidates) == 0:
        ai_cands = _ai_extract_candidates(text, language)
        candidates.extend(ai_cands)

    return candidates


def _normalize_value(key: str, raw: str) -> Optional[any]:
    """Normalize extracted value by key type."""
    raw = raw.strip()
    if key in ("sleep_duration_hours",):
        try:
            f = float(raw.replace(",", "."))
            if 0 < f <= 24:
                return f
        except ValueError:
            pass
        return None
    if key in ("steps_count", "exercise_minutes",):
        try:
            i = int(raw.replace(",", ""))
            if 0 <= i <= 100000:
                return i
        except ValueError:
            pass
        return None
    if key in ("mood", "sleep_quality", "activity_level", "stress_level",):
        return raw[:100] if len(raw) <= 100 else raw[:97] + "..."
    if key in ("bedtime", "wake_time",):
        return raw[:20]
    if key == "medications":
        return raw[:300]
    return raw[:200]


def _ai_extract_candidates(text: str, language: str) -> List[CandidateFact]:
    """Optional AI extraction; bounded, strict schema. Returns list of CandidateFact."""
    try:
        from openai import OpenAI
        client = OpenAI()
        prompt = f"""Extract lifestyle facts from this text. Return ONLY a JSON array of objects.
Each object: {{"domain":"sleep|activity|medication|mood","key":"...","value":...}}
Allowed domains: sleep, activity, medication, mood.
Keys: sleep_duration_hours, sleep_quality, steps_count, exercise_minutes, mood, stress_level, medications.
Only extract EXPLICIT statements. No inference. Max 3 facts. If none, return [].
Text: {text[:500]}"""
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        content = (r.choices[0].message.content or "").strip()
        arr = json.loads(content) if content.startswith("[") else []
        candidates = []
        for obj in arr[:3]:
            if not isinstance(obj, dict):
                continue
            domain = obj.get("domain", "")
            key = obj.get("key", "")
            value = obj.get("value")
            if domain not in ALLOWED_DOMAINS_V1 or not key or value is None:
                continue
            fact_domain = _fact_domain(domain, key)
            candidates.append(CandidateFact(
                domain=domain,
                key=key,
                value=value,
                confidence=0.75,
                is_explicit=True,
                fact_domain=fact_domain,
                fact_key=key,
            ))
        return candidates
    except Exception:
        return []


def store_candidates_and_auto_commit(
    db: Session,
    user_id: int,
    candidates: List[CandidateFact],
    source_memory_id: Optional[int] = None,
) -> dict:
    """
    Store candidates; auto-commit those with is_explicit and confidence >= 0.85.
    Returns {stored: N, auto_committed: N}.
    """
    from backend.app.models import UserFactCandidate
    from backend.app.services.i6.consent_service import ConsentDenied
    from backend.app.services.i6.memory_writes import MemoryWriteError, write_fact
    from backend.app.services.memory.memory_contract import MemoryContract

    stored = 0
    auto_committed = 0

    for c in candidates:
        if c.domain not in ALLOWED_DOMAINS_V1:
            continue
        value_json = json.dumps(c.value)
        cand = UserFactCandidate(
            user_id=user_id,
            domain=c.fact_domain,
            key=c.fact_key,
            value_json=value_json,
            source_memory_id=source_memory_id,
            confidence=c.confidence,
            is_explicit=c.is_explicit,
            status="pending",
        )
        db.add(cand)
        db.flush()
        stored += 1

        if c.is_explicit and c.confidence >= 0.85:
            valid, _ = MemoryContract.validate_fact(c.fact_domain, c.fact_key)
            if valid:
                try:
                    write_fact(
                        db,
                        user_id,
                        c.fact_domain,
                        c.fact_key,
                        c.value,
                        source="chat",
                        provenance_class="USER_STATED",
                        commit=False,
                    )
                    cand.status = "accepted"
                    auto_committed += 1
                except (ConsentDenied, MemoryWriteError):
                    pass

    db.commit()
    return {"stored": stored, "auto_committed": auto_committed}
