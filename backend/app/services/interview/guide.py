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
_SFX = r"(?:م|ت|ش|ی|ان|ها|هایم|هایش|مان|تان|شان)?"  # Persian possessive / plural clitics
_PAIN = re.compile(
    r"(?<!\w)(?:درد|سوزش|گرفتگی|تپش|خفقان|سرگیجه|تهوع|تنگی\s*نفس|خارش|ورم|تب|سرفه|بی\s*حال|ضعف|لرز)" + _SFX + r"(?!\w)|"
    r"\b(?:pain|hurts?|ache|aching|dizzy|nausea|palpitations?|short of breath|fever|cough|swelling|itch|symptom)s?\b|"
    r"(?<!\w)(?:ألم|يؤلم|دوخة|غثيان|خفقان|ضيق في التنفس|حمى|سعال|تورم|حكة)(?:ني|ي|ه|ها|ك|نا|ات|ان)?(?!\w)",
    re.I,
)
_CLAUSES = re.compile(r"[،,؛;.!?؟\n]+|\s(?:ولی|اما|اگرچه|but|however|although)\s", re.I)


# not a complaint: the Persian thank-you idiom, a denial («I have no pain»), a definition/information question
_NOT_A_COMPLAINT = re.compile(
    r"(?:دست(?:ت|تون|ش|م)?\s*درد\s*نکن(?:ه|د)|درد\s*نکنه|دست\s*مریزاد|"
    r"\b(?:no|without|never|not|don'?t|doesn'?t|haven'?t|hasn'?t)\s+(?:(?:have|had|feel|any)\s+)*(?:pain|ache|fever|cough|symptoms?)\b|"
    r"\b(?:what|why|how|when)\s+(?:does|do|is|are|can|should|to)\b.{0,40}\b(?:mean|cause|treat|cure|symptoms?)\b|"
    r"\bwhat\s+is\s+(?:a\s+)?(?:fever|pain|cough|nausea)\b|"
    r"(?:بدون|هیچ|بی)\s*(?:درد|تب|سرفه|تهوع)|(?:درد|تب|سرفه)\s*(?:ندارم|ندارد|نیست)|"
    r"(?:یعنی\s*چی|به\s*چه\s*معنی|چیست|چی\s*هست)\b|"
    r"(?:ليس|لا)\s+(?:لدي|عندي)\s+(?:ألم|حمى|سعال)|ما\s+معنى)",
    re.I,
)


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def detect_topics(message: str, language: str = "fa") -> set[str]:
    """{'symptom', 'work_life'} - the interview topics this message is about (may be both, may be neither)."""
    text = message or ""
    out: set[str] = set()
    # per CLAUSE: a thanks idiom / denial / information question in ONE clause must not hide a real complaint in another (Codex P2)
    if any(c.strip() and not _NOT_A_COMPLAINT.search(c) and _PAIN.search(c) for c in _CLAUSES.split(text)):
        out.add("symptom")
    elif not _NOT_A_COMPLAINT.search(text):
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


def care_picture(db: Any, user_id: int, language: str = "fa") -> tuple[int, str]:
    """(open follow-up chains, ONE line of the care picture) through the shared CareState (R-108): the chat reads the same picture the
    reports and notifications read, so it cannot say «nothing is wrong» while a follow-up is open. (0, "") on any problem or no consent."""
    try:
        from backend.app.services.care_state import get_care_state, summary_line

        state = get_care_state(db, user_id)
        if state is None:
            return 0, ""
        return len(state.follow_ups), summary_line(state, language)
    except Exception:  # noqa: BLE001
        return 0, ""


def open_care_follow_ups(db: Any, user_id: int) -> int:
    return care_picture(db, user_id)[0]


REASON_HINT_PREFIX = "REASON ANSWER (R-112)"
NO_DOCTOR_PREFIX = "NO DOCTOR YET (R-112 am.1)"

# «I have not seen a doctor (yet)» in the user's own words
_NO_DOCTOR = re.compile(
    r"(?:(?:هنوز|تا\s*حالا|تاحالا)\s*)?(?:به\s*)?(?:پیش\s*)?(?:دکتر|پزشک|متخصص)\s*(?:هم\s*)?(?:نرفتم|نرفته\s*ام|نرفته‌ام|ندیدم|نمی\s*رفتم)"
    r"|(?:نرفتم|نرفته‌ام|نرفته\s*ام)\s*(?:پیش\s*)?(?:دکتر|پزشک|متخصص)"
    r"|(?:no|not)\s+(?:doctor|dr)\s+yet|(?:not|never)\s+(?:seen|been\s+to|visited)\s+(?:a\s+|the\s+|any\s+)?(?:doctor|physician|specialist)|haven'?t\s+(?:seen|been\s+to|visited|gone\s+to|consulted)\s+(?:a\s+|the\s+|any\s+)?(?:doctor|physician|dermatologist|specialist|gp)"
    r"|(?:did\s*n'?t|did\s+not|have\s+not|haven'?t)\s+(?:see|seen|visit|visited|go|gone)\s+(?:a\s+|the\s+)?(?:doctor|physician|specialist)"
    r"|لم\s+(?:أذهب|اذهب|أزر|ازر|أراجع|اراجع)\s+(?:إلى|الى|ل)?\s*(?:ال)?(?:طبيب|دكتور)",
    re.IGNORECASE,
)


def says_no_doctor_yet(message: str) -> bool:
    return bool(_NO_DOCTOR.search((message or "").replace("\u200c", " ")))


def no_doctor_hint(db: Any, user_id: int, message: str, language: str = "fa") -> Optional[str]:
    """R-112 am.1 (Javad 2026-11-21: «اگر کاربر بگوید دکتر نرفته‌ام»): no judgement, why a visit helps for THIS problem, ONE direct offer to
    find the specialist (named when known), the practical steps go on, the reason is not asked again. Never raises."""
    try:
        if not says_no_doctor_yet(message):
            return None
        from backend.app.services.i5 import specialty_lexicon as sl

        problem, spec = "", None
        try:
            from backend.app.services.care_state import get_care_state

            state = get_care_state(db, user_id)
            if state is not None and state.issues:
                problem = state.issues[0].text
                spec = sl.find_specialty(problem)
        except Exception:  # noqa: BLE001
            pass
        if spec is None:
            try:
                from backend.app.services.i6.consent_service import PERM_READ, has_permission_readonly
                from backend.app.services.i7.retention import query_eligible_raw

                if not has_permission_readonly(db, user_id, PERM_READ):
                    raise PermissionError("memory read consent is missing")  # past conversations are NOT read without consent (Codex P1)
                for row in query_eligible_raw(db, user_id, limit=6) or []:
                    spec = sl.find_specialty(str(getattr(row, "user_message", "") or ""))
                    if spec:
                        break
            except Exception:  # noqa: BLE001
                pass
        about = f" for «{problem}»" if problem else ""
        ask = f"«do you want me to find a {spec} specialist in your area?» (say the specialty in the user's language)" if spec else "«do you want me to find the right specialist in your area?»"
        return (
            f"{NO_DOCTOR_PREFIX}. The user says they have not seen a doctor yet{about}. Do NOT judge, scold or press. Reply compact, in this order: "
            "(1) ONE line on why a visit helps for THIS problem and what the doctor usually checks (name the 2-3 typical checks only when you know them "
            "well - e.g. hair loss: iron stores/ferritin, thyroid, vitamin D, hormones, stress; otherwise say it plainly without inventing tests). "
            f"(2) Ask ONE direct question: {ask} - no softeners, no menu of offers (R-049). "
            "(3) Keep giving the practical non-drug steps with their how-to while they decide. "
            "(4) One explicit «see a doctor soon / emergency if ...» line only when a red flag fits. "
            "(5) Do not ask the reason or the doctor question again; never diagnose; never start/stop/change a medicine."
        )
    except Exception:  # noqa: BLE001
        return None


def reason_hint(db: Any, user_id: int, language: str = "fa", message: Optional[str] = None) -> Optional[str]:
    """R-112 (Javad 2026-11-21): the user's message answers «what do you take it for?». The model answers like a caretaker: the schedule
    confirmation, a reflection, clinician questions, practical non-drug steps WITH the how-to, age-aware, diet + exercise, a follow-up.
    The facts (name, times, age) come from memory; None when the last Sedi reply was not that question. Never raises."""
    try:
        from backend.app.services.medication_care import chat_reminder as _mc

        ctx = _mc.reason_context(db, user_id, language, message=message)
        if ctx is None:
            return None
        times = "، ".join(ctx.get("times") or []) if language in ("fa", "ar") else ", ".join(ctx.get("times") or [])
        age = ""
        try:
            from backend.app.services.user_context.user_state import get_user_state

            state = get_user_state(db, user_id)
            if state is not None and state.age:
                age = f"{state.age}" + (f", {state.sex}" if state.sex else "")
        except Exception:  # noqa: BLE001
            age = ""
        return (
            f"{REASON_HINT_PREFIX}. The user's message tells you WHY they take «{ctx.get('name')}»"
            + (f" (registered at {times})" if times else "")
            + ". Answer like a careful, warm caretaker whose goal is CONTINUOUS follow-up and care, compact, in this order: "
            + (f"(1) ONE short line confirming «{ctx.get('name')}» is registered at {times}. " if times else "(1) ONE short line saying it is registered. ")
            + "(2) ONE line reflecting their reason in their own words. "
            "(3) If the reason is a health or appearance PROBLEM (hair, skin, sleep, energy, digestion, mood, pain, immunity ...) and not only «the "
            "doctor told me», ask like a clinician - at most THREE short questions together: did you see a doctor for it and what did they say; is "
            "there stress or another change (sleep, diet, illness, family history, a new medicine); since when. "
            "(4) Give 2-3 practical NON-DRUG management steps and for EACH say HOW to do it (how often, how long, concrete foods, amounts or "
            "exercise); add suitable food and exercise suggestions in a short line. "
            + (f"Use the user's age and sex ({age}): say plainly what is normal at that age and what is not. " if age else "Their age is unknown: ask it as one of the questions. ")
            + "(5) Never diagnose, never start/stop/change a medicine or dose; one explicit «see a doctor / emergency if ...» line when it fits. "
            + (
                "(6) End with a concrete follow-up promise (what you will ask them tomorrow). "
                if ctx.get("tracked")
                else "(6) No follow-up could be tracked: do NOT promise a check-in tomorrow; invite them to tell you how it goes. "
            )
            + "Speak with certainty, no hedging offers, no disclaimers."
        )
    except Exception:  # noqa: BLE001
        return None


def build_hint(topics: set[str], gaps: list[str], open_follow_ups: int, care_line: str = "") -> Optional[str]:
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
    if care_line:
        parts.append(
            "CARE PICTURE (from this user's own memory; stay consistent with it and never contradict it - e.g. never say nothing is "
            f"wrong while a follow-up is open): {care_line}."
        )
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
        follow_ups, care_line = care_picture(db, user_id, language)
        base = build_hint(topics, gaps, follow_ups, care_line)
        reason = reason_hint(db, user_id, language, message)  # R-112: the answer to «what do you take it for?»
        no_doctor = no_doctor_hint(db, user_id, message, language)  # R-112 am.1: «دکتر نرفته‌ام»
        return "\n".join(p for p in (no_doctor, reason, base) if p) or None
    except Exception:  # noqa: BLE001
        logger.exception("[R-109] interview guide skipped")
        return None
