# backend.app.services.knowledge.llm_memory_extractor_v2
"""R-021 / M2: smart (LLM) extraction of what the user says about themselves — with DETERMINISTIC validation.

The model only PROPOSES. Nothing it returns is stored unless every item passes the validator:
- allowed keys only (mapped onto the existing KC → I6 promotion path and the I7 life timeline; no new store),
- every item carries an ``evidence`` quote that must appear verbatim (after normalisation) in the user's own message,
- a condition said about a RELATIVE can never become the user's own condition,
- bounded sizes, poison/unsupported-medical-inference checks stay in ``write_fact``,
- memory consent is checked by the same writers (no consent → nothing stored).
Off by default (``SEDI_MEMORY_LLM_EXTRACTION_ENABLED``); runs in a background thread after the reply, fail-open, rate-limited.
The deterministic extractors (stated_facts_extractor_v1) remain as the first line and as the safety net.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from backend.app.services.knowledge.conversation_extractor_v1 import ExtractedCandidate

logger = logging.getLogger(__name__)

# model key -> (KC fact_type understood by candidate_promotion_service, list_like)
ALLOWED_FACTS: dict[str, tuple[str, bool]] = {
    "health_concerns": ("health_concerns", True),
    "family_history": ("family_history", True),
    "allergies": ("intake_allergies", True),
    "occupation": ("occupation_stated", False),
    "household": ("household_context", False),
    "interests": ("interests", True),
    "goal": ("intake_goal", False),
    "food_preferences": ("intake_food_preferences", True),
    "exercise_preferences": ("intake_exercise_preferences", True),
    "sleep_hours": ("sleep_duration_hours", False),
}
MAX_LIST_ITEMS = 8
MAX_ITEM_CHARS = 60
MAX_STRING_CHARS = 90
MAX_EVENTS = 4
MIN_MESSAGE_CHARS = 20
_CARE_KINDS = frozenset({"loss", "job_loss", "separation", "surgery", "accident"})
_RELATIVES = (
    "مادرم", "پدرم", "همسرم", "خواهرم", "برادرم", "فرزندم", "مادربزرگم", "پدربزرگم", "مادر من", "پدر من",
    "my mother", "my father", "my mom", "my dad", "my sister", "my brother", "my wife", "my husband", "my son", "my daughter",
)

SYSTEM_PROMPT = """You extract MEMORY from ONE message a user wrote to their health companion. Output JSON only.
Rules:
- Only what the USER explicitly states about THEMSELVES or their close relatives. Never infer, guess, diagnose or add facts.
- Every item needs "evidence": an exact quote (copy-paste) from the message that supports it.
- "health_concerns": conditions, symptoms or problems of the USER (e.g. hair loss). A condition of a relative goes ONLY in "family_history" as "mother: diabetes".
- Skip questions, hypotheticals, negations ("I don't have X"), jokes and anything the user is unsure about.
- Keep values short, in the user's language. Do not copy sentences.
Schema:
{"facts":[{"key":"health_concerns|family_history|allergies|occupation|household|interests|goal|food_preferences|exercise_preferences|sleep_hours","value":"string or [strings]","evidence":"exact quote"}],
 "events":[{"kind":"loss|job_loss|separation|surgery|accident|diagnosis|medication_change|procedure|move|milestone|other","subject":"self|mother|father|spouse|child|sibling|relative|friend|other","summary":"<=100 chars neutral","when":"words about when, or empty","evidence":"exact quote"}]}
If nothing qualifies return {"facts":[],"events":[]}."""


def llm_extraction_enabled() -> bool:
    return (os.environ.get("SEDI_MEMORY_LLM_EXTRACTION_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"))


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("‌", " ").replace("‍", "").replace("ي", "ی").replace("ك", "ک")
    t = re.sub(r"[ً-ْـ]", "", t)
    t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    return " ".join(t.split())


def _evidence_ok(evidence: Any, message_norm: str) -> bool:
    ev = _norm(str(evidence or ""))
    return len(ev) >= 2 and ev in message_norm


def _clean_item(v: Any) -> str:
    return " ".join(str(v or "").split()).strip(" .،,؛;")


def _value_for(key: str, raw: Any) -> Any:
    """Validated value (list for list-like keys, str otherwise) or None."""
    _ft, list_like = ALLOWED_FACTS[key]
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    cleaned = [_clean_item(i) for i in items]
    cleaned = [c for c in cleaned if c and len(c) <= (MAX_ITEM_CHARS if list_like else MAX_STRING_CHARS)]
    if not cleaned:
        return None
    if key == "sleep_hours":
        m = re.search(r"\d{1,2}", _norm(cleaned[0]))
        hours = int(m.group(0)) if m else 0
        return hours if 1 <= hours <= 14 else None
    if list_like:
        out: list[str] = []
        for c in cleaned:
            if c not in out:
                out.append(c)
        return out[:MAX_LIST_ITEMS]
    return cleaned[0]


def _about_relative(evidence: str) -> bool:
    e = _norm(evidence)
    return any(r in e for r in _RELATIVES)


def parse_and_validate(raw_text: str, message: str) -> tuple[list[ExtractedCandidate], list[dict[str, Any]]]:
    """Strict: anything unexpected is dropped, never repaired. Returns (candidates, events)."""
    try:
        start, end = raw_text.index("{"), raw_text.rindex("}") + 1
        data = json.loads(raw_text[start:end])
    except (ValueError, TypeError, AttributeError):
        return [], []
    if not isinstance(data, dict):
        return [], []
    msg = _norm(message)
    candidates: list[ExtractedCandidate] = []
    seen: set[tuple[str, str]] = set()
    for item in (data.get("facts") or [])[:12]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key not in ALLOWED_FACTS or not _evidence_ok(item.get("evidence"), msg):
            continue
        if key == "health_concerns" and _about_relative(str(item.get("evidence"))):
            continue  # a relative's condition is never the user's own
        value = _value_for(key, item.get("value"))
        if value is None:
            continue
        sig = (key, json.dumps(value, ensure_ascii=False, sort_keys=True))
        if sig in seen:
            continue
        seen.add(sig)
        candidates.append(
            ExtractedCandidate(
                fact_key=ALLOWED_FACTS[key][0],
                fact_value=value,
                confidence=0.9,
                evidence=_clean_item(item.get("evidence"))[:200],
                pattern_id="llm_memory_v2",
            )
        )
    from backend.app.services.i7.life_events import KINDS, SUBJECTS

    events: list[dict[str, Any]] = []
    for item in (data.get("events") or [])[:MAX_EVENTS]:
        if not isinstance(item, dict):
            continue
        kind, subject = str(item.get("kind") or "").strip(), str(item.get("subject") or "other").strip()
        if kind not in KINDS or subject not in SUBJECTS or not _evidence_ok(item.get("evidence"), msg):
            continue
        summary = _clean_item(item.get("summary"))[:100]
        events.append(
            {
                "kind": kind,
                "subject": subject,
                "summary": summary or None,
                "when": _clean_item(item.get("when"))[:60],
                "evidence": _clean_item(item.get("evidence"))[:200],
            }
        )
    return candidates, events


def parse_when(when_text: str, now: Optional[datetime] = None) -> tuple[datetime, str]:
    """Rough, honest date from the user's own words: (naive UTC datetime, precision)."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    w = _norm(when_text)
    if not w:
        return now, "approx"
    if any(x in w for x in ("دیروز", "yesterday", "البارحة", "امس")):
        return now - timedelta(days=1), "day"
    if any(x in w for x in ("امروز", "today", "اليوم")):
        return now, "day"
    if any(x in w for x in ("هفته پیش", "last week", "الأسبوع الماضي", "هفته ی پیش")):
        return now - timedelta(days=7), "approx"
    if any(x in w for x in ("ماه پیش", "last month", "الشهر الماضي")):
        return now - timedelta(days=30), "approx"
    if any(x in w for x in ("پارسال", "last year", "العام الماضي", "سال پیش")):
        return now - timedelta(days=365), "year"
    m = re.search(r"\b(13\d{2}|14\d{2}|19\d{2}|20\d{2})\b", w)
    if m:
        y = int(m.group(1))
        y = y + 621 if y < 1700 else y
        if 1900 <= y <= now.year:
            return datetime(y, 6, 30), "year"
    return now, "approx"


def apply_extraction(
    db: Any,
    user_id: int,
    candidates: list[ExtractedCandidate],
    events: list[dict[str, Any]],
    language: str = "fa",
) -> dict[str, int]:
    """Store validated items through the SAME governed paths as every other writer (consent-gated there)."""
    stored = {"facts": 0, "events": 0}
    if candidates:
        from backend.app.services.knowledge.conversation_extraction_service import process_message

        res = process_message(db, user_id, "", language, extra_candidates=candidates)
        stored["facts"] = int(res.get("created_candidates_count", 0))
    if events:
        from backend.app.services.candidate_promotion_service import _promote_care_checkin
        from backend.app.services.i7.life_events import record_life_event

        for ev in events:
            when, precision = parse_when(ev.get("when") or "")
            rec = record_life_event(
                db, user_id, kind=ev["kind"], summary=ev.get("summary"), occurred_at=when, precision=precision,
                subject=ev["subject"], source="conversation", evidence=ev.get("evidence"),
            )
            if rec is not None:
                stored["events"] += 1
                if ev["kind"] in _CARE_KINDS:
                    _promote_care_checkin(db, user_id, ev["kind"])
    return stored


def _call_llm(message: str) -> str:
    from backend.app.core.conversation import prompts

    model = (os.environ.get("SEDI_MEMORY_EXTRACTION_MODEL") or "").strip() or prompts.resolve_openai_chat_model()
    resp = prompts.client.responses.create(
        model=model,
        input=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": message}],
        reasoning={"effort": "low"},
    )
    return (resp.output_text or "").strip()


def run_llm_extraction(
    db: Any,
    user_id: int,
    message: str,
    language: str = "fa",
    *,
    llm_call: Optional[Callable[[str], str]] = None,
) -> dict[str, int]:
    """One extraction pass (synchronous). Returns counts; never raises."""
    try:
        from backend.app.services.i6.consent_service import PERM_WRITE, has_permission

        if not has_permission(db, user_id, PERM_WRITE):  # no memory.write: do not even call the model
            return {"facts": 0, "events": 0}
        raw = (llm_call or _call_llm)(message)
        candidates, events = parse_and_validate(raw, message)
        if not candidates and not events:
            return {"facts": 0, "events": 0}
        return apply_extraction(db, user_id, candidates, events, language)
    except Exception:
        logger.exception("llm memory extraction failed (non-critical)")
        return {"facts": 0, "events": 0}


_last_run: dict[int, float] = {}
_RATE_SECONDS = 8.0


def _worth_extracting(message: str) -> bool:
    t = " ".join((message or "").split())
    if len(t) < MIN_MESSAGE_CHARS:
        return False
    return not (t.endswith(("؟", "?")) and len(t) < 60)


def schedule_llm_extraction(user_id: int, message: str, language: str = "fa") -> bool:
    """Fire-and-forget background pass after the chat reply. Off unless the flag is on; True when a thread was started."""
    if not llm_extraction_enabled() or not _worth_extracting(message):
        return False
    now = time.monotonic()
    if now - _last_run.get(user_id, 0.0) < _RATE_SECONDS:
        return False
    _last_run[user_id] = now

    def _work() -> None:
        try:
            from backend.app.database import SessionLocal

            gen = SessionLocal()
            db = next(gen)
            try:
                run_llm_extraction(db, user_id, message, language)
            finally:
                try:
                    gen.close()
                except Exception:
                    pass
        except Exception:
            logger.exception("llm memory extraction thread failed (non-critical)")

    threading.Thread(target=_work, name="sedi-memory-extraction", daemon=True).start()
    return True
