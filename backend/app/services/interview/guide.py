"""R-109 step 1b-1: the data-driven interview guide - Sedi converses precisely, in detail, about EVERYTHING (illness to work and life)
until she understands the user, and what she learns lands in memory.

Division of labour (no second owner, R-005):
  * this module = the deterministic SKELETON: which topic the turn is about, what a careful interviewer must cover for it, which
    memory slots (I6 keys, consent-gated read) are still empty, and whether an open care follow-up wants a «how are you now?»;
  * the chat model = the VOICE: it receives the skeleton as one system hint and asks up to THREE short, grouped questions;
  * the existing extraction (KC + LLM memory extractor v2 -> candidate_promotion -> I6 write_fact) = the WRITE path for the answers.
Safety first: an emergency red flag or a self-harm turn is owned by their own paths - this guide stays silent for them.
Fail-open; kill switch SEDI_INTERVIEW_GUIDE_DISABLED (code default ON, no env change).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

DISABLED_ENV = "SEDI_INTERVIEW_GUIDE_DISABLED"
MAX_QUESTIONS = 3  # R-105

# What a careful clinician-companion covers for a symptom (skip what the conversation already answered), in this order.
SYMPTOM_CHECKLIST: tuple[str, ...] = (
    "how it is RIGHT NOW (present at this moment? how strong, 0-10?)",
    "when it started and how it behaves (constant or in episodes, how long each lasts, how often)",
    "what triggers it or eases it (activity, rest, food, stress, position, time of day)",
    "what else comes with it (breathing, sweating, nausea, dizziness, fever, palpitations - anything relevant to this area)",
    "has it happened before - when, what happened then, what was done",
    "what the user already did or took for it so far (listen without judging)",
    "what the user thinks caused it, or what changed in their life/work/sleep before it began",
)

# Memory slots that complete the picture: (domain, key, what to learn). A slot is a gap when no ACTIVE fact exists for it.
SYMPTOM_BACKGROUND: tuple[tuple[str, str, str], ...] = (
    ("medical", "health_concerns", "known illnesses or ongoing health problems (blood pressure, diabetes, cholesterol, heart, thyroid...)"),
    ("medical", "family_history", "close relatives with the same or a serious related problem"),
)
WORK_LIFE_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("work", "occupation", "what work the user does"),
    ("work", "work_schedule", "working days and hours, shifts"),
    ("work", "work_stressors", "what weighs on them at work (pressure, boss, workload, job security)"),
    ("social", "household_context", "who they live with / family situation"),
    ("social", "support_network", "who supports them when things are hard"),
    ("routines", "wake_time", "usual wake-up time"),
    ("routines", "bedtime", "usual bedtime"),
    ("barriers", "time_constraints", "what limits their time for self-care"),
)

_WORK_LIFE = re.compile(
    r"(?:کار|شغل|محل ?کار|رئیس|همکار|اضافه ?کاری|شیفت|استعفا|بیکار|اخراج|حقوق|کارمند|کسب ?و ?کار|"
    r"خانواده|همسر|زن ?م|شوهر|فرزند|بچه ?ها|مادر|پدر|طلاق|تنها|تنهایی|مشکل ?مالی|بدهی|"
    r"\b(?:job|work|boss|colleague|shift|overtime|laid off|fired|salary|career|family|wife|husband|kids|children|divorce|lonely|debt)\b|"
    r"الوظيفة|المدير|زميل|العمل|الأسرة|الزوج|الزوجة|الأولاد|الطلاق|وحيد|ديون)",
    re.I,
)
_PAIN = re.compile(
    r"(?:درد|سوزش|گرفتگی|تپش|خفقان|سرگیجه|تهوع|تنگی نفس|خارش|ورم|تب|سرفه|بی ?حال|ضعف|لرز|"
    r"\b(?:pain|hurts?|ache|aching|dizzy|nausea|palpitations?|short of breath|fever|cough|swelling|itch|symptom)s?\b|"
    r"ألم|يؤلم|دوخة|غثيان|خفقان|ضيق في التنفس|حمى|سعال|تورم|حكة)",
    re.I,
)


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def detect_topics(message: str, language: str = "fa") -> set[str]:
    """{'symptom', 'work_life'} - the interview topics this message is about (may be both, may be neither)."""
    text = message or ""
    out: set[str] = set()
    if _PAIN.search(text):
        out.add("symptom")
    else:
        try:
            from backend.app.services.care_navigation import symptom_triage

            if symptom_triage.triage(text, language).areas:
                out.add("symptom")
        except Exception:  # noqa: BLE001
            pass
    if _WORK_LIFE.search(text):
        out.add("work_life")
    return out


def _known_keys(db: Any, user_id: int, domains: set[str]) -> set[tuple[str, str]]:
    """(domain, key) of every ACTIVE, consented fact (read-only, fail-open to nothing known -> we simply ask)."""
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

    known: set[tuple[str, str]] = set()
    for domain in domains:
        try:
            for fact in list_facts_readonly_or_empty(db, user_id, domain=domain):
                known.add((fact.domain, fact.key))
        except Exception:  # noqa: BLE001
            continue
    return known


def memory_gaps(db: Any, user_id: int, topics: set[str]) -> list[str]:
    """What is still unknown about this user for the turn's topics, most useful first."""
    wanted: list[tuple[str, str, str]] = []
    if "symptom" in topics:
        wanted += list(SYMPTOM_BACKGROUND)
    if "work_life" in topics:
        wanted += list(WORK_LIFE_SLOTS)
    if not wanted:
        return []
    known = _known_keys(db, user_id, {d for d, _k, _w in wanted})
    return [what for d, k, what in wanted if (d, k) not in known]


def open_care_follow_ups(db: Any, user_id: int) -> int:
    try:
        from backend.app.services.i10.commitment_followup import open_commitment_count

        return int(open_commitment_count(db, user_id))
    except Exception:  # noqa: BLE001
        return 0


def build_hint(topics: set[str], gaps: list[str], open_follow_ups: int) -> Optional[str]:
    """The ONE system hint (English; the model answers in the user's language). None when there is nothing to guide."""
    parts: list[str] = []
    if "symptom" in topics:
        parts.append(
            "SYMPTOM INTERVIEW (R-109). The user brings a symptom. Be a careful, warm clinician-companion: one short empathy line, then "
            "learn the picture. Cover these, SKIPPING whatever the conversation already answered (never ask twice): "
            + "; ".join(f"({i + 1}) {c}" for i, c in enumerate(SYMPTOM_CHECKLIST))
            + ". Start with the current state. Do NOT diagnose and do not use disclaimer wording; interim care, if any, is non-drug only "
            "with an explicit «go to emergency now if…» line; never start/stop/change a medicine."
        )
    if "work_life" in topics:
        parts.append(
            "LIFE/WORK INTERVIEW (R-109). The user talks about work or family life. Listen first (one empathy line), then learn the "
            "situation precisely - what exactly happened, since when, how it affects sleep/mood/health - because it is part of the whole picture."
        )
    if gaps:
        parts.append("STILL UNKNOWN about this user (ask only when it fits the flow): " + "; ".join(gaps[:5]) + ".")
    if open_follow_ups > 0 and ("symptom" in topics or "work_life" in topics or not topics):
        parts.append(
            f"OPEN CARE FOLLOW-UP: the user has {open_follow_ups} open care follow-up(s). Include ONE short question about how they are "
            "doing NOW (e.g. «الان وضعیتت چطور است؟») unless your previous reply already asked it."
        )
    if not parts:
        return None
    parts.append(
        f"FORM: ask at most {MAX_QUESTIONS} short, concrete questions, together at the end of your reply, only the most useful unanswered ones; "
        "never repeat something the user already told you; keep the reply compact (no long lists)."
    )
    return "\n".join(parts)


def hint_for_turn(db: Any, user_id: int, message: str, language: str = "fa") -> Optional[str]:
    """The interview hint for this turn, or None (disabled, emergency, self-harm, nothing to guide). Never raises."""
    try:
        if not enabled() or not (message or "").strip():
            return None
        from backend.app.services.care_navigation import crisis_support, symptom_triage

        if symptom_triage.triage(message, language).red_flag:
            return None  # an emergency is owned by the safety path
        if crisis_support.hint_for_turn(db, user_id, message, language):
            return None  # self-harm support keeps its single gentle question (R-099)
        topics = detect_topics(message, language)
        gaps = memory_gaps(db, user_id, topics) if topics else []
        return build_hint(topics, gaps, open_care_follow_ups(db, user_id))
    except Exception:  # noqa: BLE001
        logger.exception("[R-109] interview guide skipped")
        return None
