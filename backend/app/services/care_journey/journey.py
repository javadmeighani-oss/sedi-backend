"""R-109 step 1b-2: the CARE JOURNEY on the provider-finding path.

The doctor/lab finder answers from deterministic text and never reaches the chat model, so the interview guide (1b-1) and the
commitment capture (A3) never ran there: a user who said «a heart doctor in Pardis» got links and nothing else (pilot 2026-11-20:
no follow-up task, no episode, no «what happened / new or old / why / what to do until the visit»).

This module is the missing piece, built ONLY on existing owners (R-005):
  * the follow-up itself = a CareFollowUpTask commitment of the I10 loop (``commitment_followup.create_journey_followup``: hour-level
    due times by urgency tier, quiet hours, daily cap, one chain per tier, the worker that already ticks every 10 minutes);
  * what the user answers = I6 ``medical.symptom_episodes`` (deterministic write, consent-gated, no dependence on LLM extraction);
  * the text = the catalog (3 languages): conservative NON-DRUG stabilising care + an explicit emergency line, and up to THREE grouped
    interview questions (R-105).
Emergency red flags and self-harm are owned by their own paths: no journey is started for them.
Fail-open; kill switch SEDI_CARE_JOURNEY_DISABLED (code default ON, no env change).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.app import sedi_copy

logger = logging.getLogger(__name__)

DISABLED_ENV = "SEDI_CARE_JOURNEY_DISABLED"
MARKER_KEY = "journey.markers.interview"
FOLLOWUP_MARKER_KEY = "journey.markers.followup"  # R-120: the questions built FROM the user's explanation (the interview's second step)
# body areas whose complaints deserve same-day check-ins (skin / dental / eye / ENT / endocrine / women stay on the routine ladder)
_SYMPTOM_AREAS = frozenset({"head", "stomach", "back_joint", "urinary", "lung", "mind", "chest", "heart_rhythm"})
_HEART = re.compile(r"قلب|قفسه|سینه|heart|cardio|chest|قلبي|صدر", re.I)


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def tier_for(text: str, language: str = "fa") -> Optional[str]:
    """'acute' (heart/chest and similar: check-ins within hours), 'soon', 'routine'; None when an emergency red flag owns the turn."""
    try:
        from backend.app.services.care_navigation import symptom_triage

        result = symptom_triage.triage(text or "", language)
        if result.red_flag:
            return None
        if _HEART.search(text or "") or {"chest", "heart_rhythm"} & set(result.areas):
            return "acute"
        if result.urgency == "soon" or set(result.areas) & _SYMPTOM_AREAS:
            return "soon"
        return "routine"
    except Exception:  # noqa: BLE001
        return "routine"


def area_of(text: str) -> str:
    return "chest" if _HEART.search(text or "") else "generic"


def journey_text(language: str, area: str, *, new_journey: bool) -> str:
    """The compact journey block: stabilising care + the grouped interview (new journey) or just the status question."""
    lang = language if language in ("fa", "ar", "en") else "en"
    if not new_journey:
        return sedi_copy.t("journey.status_only", lang)
    care = sedi_copy.t(f"journey.care.{area}", lang)
    interview = sedi_copy.t(f"journey.interview.{area}", lang)
    return care + "\n\n" + interview


def _journey_open(db: Any, user_id: int) -> bool:
    from backend.app.services.i10 import commitment_followup as cf

    return cf.open_journey_count(db, user_id) > 0


def intake_message(db: Any, user_id: int, request_text: str, language: str, *, intake_done: bool) -> Optional[str]:
    """R-109 (Javad 2026-11-20): the doctor is introduced AFTER Sedi has gathered what she wants to know, so the most suitable option is
    chosen. For a doctor/centre/lab request whose reason and place are settled, this is the grouped interview (up to three questions)
    asked BEFORE any search. The follow-up chain is tracked from this moment (even if the user never answers). None = search now
    (already asked, emergency, no memory consent, disabled, error): the user is never held up by a question Sedi cannot keep."""
    try:
        if intake_done or not enabled() or db is None:
            return None
        tier = tier_for(request_text, language)
        if tier is None:
            return None
        from backend.app.services.i10 import commitment_followup as cf

        if not _journey_open(db, user_id):
            lang3 = language if language in ("fa", "ar", "en") else "en"
            if cf.create_journey_followup(db, user_id, sedi_copy.t("journey.step", lang3), tier) is None:
                return None  # no memory-write consent: nothing is tracked, so nothing is asked or promised
            db.commit()
        lang = language if language in ("fa", "ar", "en") else "en"
        return sedi_copy.t("journey.intake.lead", lang) + "\n\n" + sedi_copy.t(f"journey.interview.{area_of(request_text)}", lang)
    except Exception:  # noqa: BLE001
        logger.exception("[R-109] journey intake skipped")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def track(db: Any, user_id: int, request_text: str, language: str) -> bool:
    """R-114: the care-journey chain is tracked WITHOUT the interview (the request was completed from memory, or the user asked not to be
    asked): the follow-up still starts, the questions are skipped. False = nothing tracked (consent, emergency, error)."""
    try:
        if not enabled() or db is None:
            return False
        tier = tier_for(request_text, language)
        if tier is None:
            return False
        if _journey_open(db, user_id):
            return True
        from backend.app.services.i10 import commitment_followup as cf

        lang3 = language if language in ("fa", "ar", "en") else "en"
        if cf.create_journey_followup(db, user_id, sedi_copy.t("journey.step", lang3), tier) is None:
            return False
        db.commit()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("[R-114] care journey not tracked")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def results_block(db: Any, user_id: int, request_text: str, language: str, explanations: Optional[list] = None) -> Optional[str]:
    """After the introduction: care until the visit of an OPEN journey (the interview was asked before). R-120 am.2: built from what the user
    explained (no fixed block, no generic «how are you now?»); the catalog block + status question only when nothing personal can be made."""
    try:
        if not enabled() or db is None or tier_for(request_text, language) is None or not _journey_open(db, user_id):
            return None
        lang = language if language in ("fa", "ar", "en") else "en"
        if explanations:
            from backend.app.services.care_journey.personal_care import personal_care_block
            from backend.app.services.i5 import specialty_lexicon as _sl

            personal = personal_care_block(explanations, lang, area_of(request_text), _sl.find_specialty(request_text))
            if personal:
                return personal
        return sedi_copy.t(f"journey.care.{area_of(request_text)}", lang)  # R-120 am.3: no generic «how are you now?» after the list
    except Exception:  # noqa: BLE001
        return None


def start(db: Any, user_id: int, request_text: str, language: str) -> Optional[str]:
    """The journey block to append to a doctor/lab answer, or None (disabled, emergency, no consent, error). Creates ONE tracked
    follow-up chain per journey (the next request while one is open only adds the «how are you now?» line)."""
    try:
        if not enabled() or db is None:
            return None
        tier = tier_for(request_text, language)
        if tier is None:
            return None
        if _journey_open(db, user_id):
            return journey_text(language, area_of(request_text), new_journey=False)
        from backend.app.services.i10 import commitment_followup as cf

        step = sedi_copy.t("journey.step", language if language in ("fa", "ar", "en") else "en")
        if cf.create_journey_followup(db, user_id, step, tier) is None:
            return None  # no memory-write consent: nothing is tracked, so nothing is promised
        db.commit()
        return journey_text(language, area_of(request_text), new_journey=True)
    except Exception:  # noqa: BLE001
        logger.exception("[R-109] care journey start skipped")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


# not an answer: thanks, refusal, topic change, a new request
_NOT_AN_ANSWER = re.compile(
    r"(?:ممنون|مرسی|متشکر|تشکر|باشه|اوکی|بیخیال|ولش|نمی\s*خوام|نه\s+ممنون|معرفی\s*کن|پیدا\s*کن|دکتر\s*دیگر|"
    r"\b(?:thanks?|thank you|ok(?:ay)?|never ?mind|cancel|forget it|find (?:me )?(?:a|an|another)|introduce|instead)\b|"
    r"شكرا|حسناً|لا أريد|ابحث|بدلاً)",
    re.I,
)
# looks like an answer about a health episode: a symptom word, or when/how-long/before wording
_EPISODE_WORDS = re.compile(
    r"(?:روز|هفته|ماه|ساعت|دقیقه|دیروز|امروز|قبل|پیش|همیشه|گاهی|هر\s*بار|وقتی|بعد\s*از|شدید|خفیف|"
    r"\b(?:since|ago|before|yesterday|today|week|day|month|hour|minute|when|after|always|sometimes|severe|mild|started|never|again)\b|"
    r"منذ|أمس|اليوم|أسبوع|شهر|ساعة|دائماً|أحياناً|بعد)",
    re.I,
)


def _answers_the_interview(answer: str, language: str = "fa") -> bool:
    if _NOT_AN_ANSWER.search(answer or ""):
        return False
    if _EPISODE_WORDS.search(answer or ""):
        return True
    try:
        from backend.app.services.interview.guide import detect_topics

        return "symptom" in detect_topics(answer or "", language)
    except Exception:  # noqa: BLE001
        return False


def is_followup_reply(sedi_reply: Optional[str]) -> bool:
    """Sedi's last reply was the interview's SECOND step (questions built from the user's explanation, R-120)."""
    text = re.sub(r"[\W_]+", "", (sedi_reply or "").lower())
    return bool(text) and any(
        re.sub(r"[\W_]+", "", marker.lower()) in text for lang in ("fa", "ar", "en") for marker in sedi_copy.variants(FOLLOWUP_MARKER_KEY, lang)
    )


def is_interview_reply(sedi_reply: Optional[str]) -> bool:
    """Sedi's last reply carried the journey interview (any language)."""
    text = re.sub(r"[\W_]+", "", (sedi_reply or "").lower())
    if not text:
        return False
    for lang in ("fa", "ar", "en"):
        for marker in sedi_copy.variants(MARKER_KEY, lang):
            if re.sub(r"[\W_]+", "", marker.lower()) in text:
                return True
    return False


# DEBT-080: «better / gone» and «worse» in the user's own words. «بهتر است دکتر بروم» (it is better to see a doctor) is not a status.
_NEG = re.compile(r"(?:نشد|نشده|نیست|نمی\s*شود|نمیشه|\bnot\b|n't|\bnever\b|(?:^|\s)(?:لم|ليس)(?:\s|$))", re.I)
_BETTER = re.compile(
    r"(?:بهتر(?:م|\s*شد(?:م|ه)?|\s*هستم|\s*شده)|حالم\s*بهتر|خوب\s*شد(?:م|ه)|خوب\s*شده|برطرف\s*شد|بر\s*طرف\s*شد|رفع\s*شد|تمام\s*شد|"
    r"دیگه\s*درد\s*(?:ندارم|نمی\s*کند)|"
    r"\b(?:feel(?:ing)?|getting|got|gotten|am|much|bit|lot) better\b|\bit(?:'s| is| has) (?:gone|stopped|passed)\b|\bno more pain\b|\bresolved\b|"
    r"تحسنت|أفضل الآن|اختفى الألم|زال الألم)",
    re.I,
)
_WORSE = re.compile(
    r"(?:بدتر(?:م|\s*شد(?:م|ه)?|\s*شده)|حالم\s*بدتر|شدیدتر\s*شد|بیشتر\s*شد|سخت\s*تر\s*شد|"
    r"\b(?:feel(?:ing)?|getting|got|much|even) worse\b|\bworse than\b|\bit(?:'s| is| has) (?:worsened|got worse|increased)\b|"
    r"ساءت|أسوأ|ازداد(?:ت)? (?:الألم|سوءا))",
    re.I,
)
_NOT_WORSE = re.compile(r"(?:نه|نبود)\s*بدتر", re.I)
# a hope, a condition, a plan or a question is not a report (Codex P1/P2, PR 199)
_HYPOTHETICAL = re.compile(
    r"(?:\b(?:hope|wish|if|when|will|would|should|could|maybe|perhaps|tomorrow|someday)\b|امیدوارم|کاش|اگر|اگه|وقتی|شاید|انشالله|ان\s*شاء|فردا|"
    r"أتمنى|ليت|إذا|عندما|غدا|ربما)",
    re.I,
)


def _negated(t: str, m: "re.Match") -> bool:
    """A negation right before or after the matched phrase (never inside it: «no more pain» is itself an improvement)."""
    return bool(_NEG.search(t[max(0, m.start() - 14): m.start()]) or _NEG.search(t[m.end(): m.end() + 14]))


def status_signal(text: str, language: str = "fa") -> Optional[str]:
    """'better' | 'worse' | None. Short, first-person status sentences only (a long message or a negated phrase is no signal)."""
    try:
        t = " ".join((text or "").replace(chr(0x200C), " ").split())
        if not t or len(t.split()) > 14:
            return None
        if "؟" in t or "?" in t or _HYPOTHETICAL.search(t):
            return None  # a question, a hope or a plan reports nothing
        from backend.app.services.knowledge.llm_memory_extractor_v2 import _about_relative

        if _about_relative(t):
            return None  # «my mother is feeling better» is not the user's status
        w = _WORSE.search(t)
        if w and not _NOT_WORSE.search(t) and not _negated(t, w):
            return "worse"
        m = _BETTER.search(t)
        if m and not _negated(t, m):
            return "better"
        return None
    except Exception:  # noqa: BLE001
        return None


APPOINTMENT_PUSH_WINDOW = timedelta(hours=24)


def _status_after_appointment_push(db: Any, user_id: int, signal: str, lang: str) -> Optional[str]:
    """R-108 / R-109 am.2 (2c-3): the user answers «how are you now?» from a care-appointment push (day-of / 2 h pre-check) while no
    journey is open. Only then (a push of the last 24 h AND a known open issue, both consent-gated) the answer is remembered: a dated
    status note on the issue, and «worse» also starts the hours-level acute chain. An unrelated «I am better» in plain chat stays untouched."""
    try:
        from backend.app import models
        from backend.app.services import care_state as cs
        from backend.app.services.i10 import commitment_followup as cf
        from backend.app.services.i10 import event_care

        horizon = datetime.utcnow() - APPOINTMENT_PUSH_WINDOW
        pushed = (
            db.query(models.Notification.id)
            .filter(models.Notification.user_id == user_id, models.Notification.is_sent.is_(True),
                    models.Notification.sent_at >= horizon,  # delivered (not queued/failed/blocked), within the window (Codex P2, PR 210)
                    models.Notification.template_key.in_((event_care.KIND_DAY_OF, event_care.KIND_PRE)))
            .first()
        )
        state = cs.get_care_state(db, user_id) if pushed else None
        if state is None or not state.issues:
            return None
        if signal == "worse" and cf.create_journey_followup(db, user_id, sedi_copy.t("journey.step", lang), "acute") is None:
            return None
        db.commit()
        _store_episode(db, user_id, f"{sedi_copy.t(f'journey.status_note.{signal}', lang)} · {datetime.utcnow().date().isoformat()}")
        return signal
    except Exception:  # noqa: BLE001
        logger.exception("[R-108] appointment-push status not applied")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None



def apply_status(db: Any, user_id: int, text: str, language: str) -> Optional[str]:
    """DEBT-080: «better» closes the open journey; «worse» replaces it with an acute chain (hours-level follow-up). Both leave a short
    I6 note. Returns 'better' / 'worse' when something changed, else None. Fail-open; commits only what it changed."""
    try:
        if db is None or not enabled():
            return None
        signal = status_signal(text, language)
        if signal is None:
            return None
        lang = language if language in ("fa", "ar", "en") else "en"
        if not _journey_open(db, user_id):
            return _status_after_appointment_push(db, user_id, signal, lang)
        from backend.app.services.i10 import commitment_followup as cf

        changed = cf.resolve_journey(db, user_id) if signal == "better" else cf.escalate_journey(db, user_id, sedi_copy.t("journey.step", lang))
        if not changed:
            db.rollback()
            return None
        db.commit()
        # the note carries its day: the episode list de-duplicates equal strings, so a second «better» (a later complaint) must differ
        _store_episode(db, user_id, f"{sedi_copy.t(f'journey.status_note.{signal}', lang)} · {datetime.utcnow().date().isoformat()}")
        return signal
    except Exception:  # noqa: BLE001
        logger.exception("[R-109] journey status not applied")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def _guide_asked(
    last_user_message: Optional[str], last_sedi_reply: Optional[str], language: str, context: Optional[list] = None
) -> bool:
    """DEBT-079: on the CHAT path the interview guide steers the model, so Sedi's question has no fixed marker. The turn counts as an
    interview when Sedi's reply asked something and the conversation so far (the previous message plus the earlier turns of the SAME
    question run, ``context``) holds a complaint (guide topic «symptom»), none of it about a relative (Codex P2, PR 199)."""
    try:
        from backend.app.services.interview.guide import detect_topics
        from backend.app.services.knowledge.llm_memory_extractor_v2 import _about_relative

        messages = [m for m in [last_user_message, *(context or [])] if m and m.strip()]
        if not messages or any(_about_relative(m) for m in messages):
            return False  # a relative's complaint: the answer is not the user's episode
        reply = last_sedi_reply or ""
        return ("؟" in reply or "?" in reply) and any("symptom" in detect_topics(m, language) for m in messages)
    except Exception:  # noqa: BLE001
        return False


def _store_episode(db: Any, user_id: int, text: str) -> bool:
    """One short I6 episode note (consent-gated; ConsentDenied = nothing stored)."""
    from backend.app.services.candidate_promotion_service import _merge_list_value
    from backend.app.services.i6.consent_service import ConsentDenied
    from backend.app.services.i6.memory_writes import write_fact

    try:
        value = _merge_list_value(db, user_id, "medical", "symptom_episodes", text)
        write_fact(db, user_id, "medical", "symptom_episodes", value, source="chat", provenance_class="USER_STATED", commit=True)
    except ConsentDenied:
        return False
    return True


def record_answer(
    db: Any,
    user_id: int,
    answer: str,
    last_sedi_reply: Optional[str],
    *,
    last_user_message: Optional[str] = None,
    language: str = "fa",
    context: Optional[list] = None,
) -> bool:
    """The user's answer to the journey interview - or to the chat-path interview guide's question about a complaint (DEBT-079) -
    becomes a short I6 episode note (deterministic, consent-gated, fail-open)."""
    try:
        if db is None or not (answer or "").strip():
            return False
        if not (is_interview_reply(last_sedi_reply) or _guide_asked(last_user_message, last_sedi_reply, language, context)):
            return False
        text = " ".join(answer.split())[:90]
        if len(text) < 3:
            return False
        from backend.app.services.knowledge.llm_memory_extractor_v2 import _about_relative

        from backend.app.services.i5.care_nav_interview import _HEALTH_NARRATIVE

        # thanks / refusal / topic change / a new request is not an episode (Codex P2, PR 196); R-120: an open explanation is
        if not (_answers_the_interview(answer, language) or (_HEALTH_NARRATIVE.search(answer) and not _NOT_AN_ANSWER.search(answer))):
            return False
        if _about_relative(answer):  # «my mother has chest pain»: not the user's episode (Codex P2, PR 196)
            return False
        return _store_episode(db, user_id, text)
    except Exception:  # noqa: BLE001
        logger.exception("[R-109] journey answer not recorded")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
