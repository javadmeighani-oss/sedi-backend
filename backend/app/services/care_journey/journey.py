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
from typing import Any, Optional

from backend.app import sedi_copy

logger = logging.getLogger(__name__)

DISABLED_ENV = "SEDI_CARE_JOURNEY_DISABLED"
MARKER_KEY = "journey.markers.interview"
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


def results_block(db: Any, user_id: int, request_text: str, language: str) -> Optional[str]:
    """After the introduction: the stabilising care + «how are you now?» of an OPEN journey (the interview was asked before)."""
    try:
        if not enabled() or db is None or tier_for(request_text, language) is None or not _journey_open(db, user_id):
            return None
        lang = language if language in ("fa", "ar", "en") else "en"
        return sedi_copy.t(f"journey.care.{area_of(request_text)}", lang) + "\n\n" + sedi_copy.t("journey.status_only", lang)
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


def record_answer(db: Any, user_id: int, answer: str, last_sedi_reply: Optional[str]) -> bool:
    """The user's answer to the journey interview becomes a short I6 episode note (deterministic, consent-gated, fail-open)."""
    try:
        if db is None or not (answer or "").strip() or not is_interview_reply(last_sedi_reply):
            return False
        text = " ".join(answer.split())[:90]
        if len(text) < 3:
            return False
        from backend.app.services.knowledge.llm_memory_extractor_v2 import _about_relative

        if not _answers_the_interview(answer):  # thanks / refusal / topic change / a new request is not an episode (Codex P2, PR 196)
            return False
        if _about_relative(answer):  # «my mother has chest pain»: not the user's episode (Codex P2, PR 196)
            return False
        from backend.app.services.candidate_promotion_service import _merge_list_value
        from backend.app.services.i6.consent_service import ConsentDenied
        from backend.app.services.i6.memory_writes import write_fact

        try:
            value = _merge_list_value(db, user_id, "medical", "symptom_episodes", text)
            write_fact(db, user_id, "medical", "symptom_episodes", value, source="chat", provenance_class="USER_STATED", commit=True)
        except ConsentDenied:
            return False
        return True
    except Exception:  # noqa: BLE001
        logger.exception("[R-109] journey answer not recorded")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
