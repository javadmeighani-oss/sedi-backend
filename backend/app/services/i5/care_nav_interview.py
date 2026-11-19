"""J3-c (R-089 amendment, D-410): ask WHY and WHICH doctor before listing doctors.

Javad, 2026-11-19, screenshot: «میخواهم یه دکتر خوب برام تو پردیس معرفی کنی» - Sedi listed general practitioners at once, without asking
what the person needs a doctor for. A caretaker first understands the REASON: for a request that names no specialty Sedi asks ONE
question (the problem, or the specialty if the person knows it). The next message completes THAT request:

  * a named specialty («نورولوژی», "dentist") is used as it is;
  * a complaint («قلبم درد می‌کند») goes through the J2 triage to the fitting specialty;
  * «نمی‌دانم» / «فرقی نمی‌کند» becomes a general practitioner.

Deterministic, no model, no new table: the pending question is recognised from Sedi's own last reply (like the specialist offer
and the reminder clarification), within 30 minutes. Fail-open: any doubt returns the message unchanged. Never raises.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.app import sedi_copy
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import specialty_lexicon as sl

ASK_KEY = "care_nav.ask_reason"
MAX_ANSWER_WORDS = 30
_NON_LETTERS = re.compile(r"[\W_]+", re.UNICODE)
_DONT_KNOW = re.compile(
    r"(?<!\S)(?:نمی ?دانم|نمیدانم|نمی ?دونم|نمیدونم)(?!\S)|فرقی ?(?:نمی ?کند|نمی ?کنه|نمیکنه|نداره|ندارد)|"
    r"(?<!\S)هر ?(?:کدام|کدوم|دکتری|کی)(?!\S)|(?<!\S)عمومی(?!\S)|"
    r"\bi don.?t know\b|\bnot sure\b|\bno idea\b|\bany (?:doctor|one|will do|is fine)\b|\banyone\b|\bwhichever\b|\bgeneral\b|"
    r"لا أعرف|أي طبيب|(?<!\S)عام(?!\S)",
    re.I,
)
_NEVERMIND = re.compile(r"ولش ?کن|بیخیال|نمی ?خواهم|نمیخوام|نمی ?خوام|لازم ?نیست|never ?mind|forget it|cancel|لا أريد|لا حاجة", re.I)


def _key(text: Optional[str]) -> str:
    return _NON_LETTERS.sub("", (text or "").lower())


def reason_question(message: str, language: str) -> Optional[str]:
    """The ONE question to ask first, or None when the request already says which kind of doctor (or is not a doctor request)."""
    try:
        if not cn.is_care_navigation_query(message):
            return None
        req = cn.parse_care_nav_request(message, language=language)
        if req.entity is not cn.CareNavEntity.SPECIALIST or req.specialty_or_service or req.name_hint:
            return None
        lang = language if language in ("fa", "ar", "en") else "en"
        return sedi_copy.t(ASK_KEY, lang)
    except Exception:  # noqa: BLE001
        return None


def is_reason_question(sedi_reply: Optional[str]) -> bool:
    """Sedi's last reply was this question (any language, any punctuation / typography)."""
    try:
        got = _key(sedi_reply)
        return bool(got) and any(_key(v) == got for lang in ("fa", "ar", "en") for v in sedi_copy.variants(ASK_KEY, lang))
    except Exception:  # noqa: BLE001
        return False


_NEGATED = re.compile(
    r"(?:\b(?:not|no|never|neither|nor|except)\b|(?<!\S)(?:نه|غیر از|به جز|بجز)(?!\S))\s+(?:\w+\s*){1,2}", re.I)


def _strip_negated(text: str) -> str:
    """«not skin, my knee hurts»: the specialty the person REJECTS is not the specialty they ask for (Codex P2)."""
    return _NEGATED.sub(" ", text)


def _specialty_for_answer(answer: str, language: str) -> Optional[str]:
    from backend.app.services.care_navigation import symptom_triage

    result = symptom_triage.triage(answer, language)
    if result.red_flag:
        return None  # an emergency (even one that names a body part) stays on the normal safety path, never a routine search (Codex P1)
    named = sl.find_specialty(_strip_negated(answer))
    if named:
        return named
    for spec in result.specialties:
        if spec != "اورژانس":
            return spec
    if result.next_question == "care_nav.q.which_area":  # «something is wrong» with no body area: a general practitioner first
        return "پزشک عمومی"
    return None


def _place_in(answer: str) -> Optional[str]:
    """A place the ANSWER itself names («نورولوژی در شیراز»): it replaces the place of the first request (Codex P2)."""
    place = cn._places.find_place(answer)
    if place.area and not place.city_inferred:
        return f"{place.area} {place.city}" if place.city else place.area
    if place.area:
        return place.area
    if place.city:
        return place.city
    return None  # only places the gazetteer knows: «pain in knee» must not turn «knee» into a city (Codex P2)


def request_for_answer(prior_request: Optional[str], sedi_reply: Optional[str], answer: str, language: str) -> Optional[str]:
    """The completed doctor request when ``answer`` replies to the reason question, else None (the message stays as it is)."""
    try:
        if not prior_request or not answer or not is_reason_question(sedi_reply):
            return None
        text = answer.strip().replace(chr(0x200c), " ")  # half-space -> space so the patterns below see «نمی دونم»
        if not text or len(text.split()) > MAX_ANSWER_WORDS or _NEVERMIND.search(text):
            return None
        if cn.is_care_navigation_query(text) and sl.find_specialty(text) and cn._has_real_location(text):
            return None  # a complete doctor request of its own (kind AND place)
        from backend.app.services.care_navigation import symptom_triage

        if symptom_triage.triage(text, language).red_flag:
            return None  # an emergency is never completed into a routine search, whatever else the answer says (Codex P1)
        spec = _specialty_for_answer(text, language)
        if spec is None and _DONT_KNOW.search(text):
            spec = "پزشک عمومی"
        if spec is None:
            return None  # an emergency or something that names no specialty: normal handling
        place = _place_in(text)
        if place:  # the answer named a (new) place: a fresh request with the specialty and THAT place
            done = f"یه دکتر {spec} در {place} معرفی کن" if language == "fa" else f"find a doctor {spec} in {place}"
        else:
            done = f"{prior_request.strip()} متخصص {spec}"
        if cn.wants_sources(text) and not cn.wants_sources(done):  # «neurology, include sources»: the source request survives (Codex P2)
            done += " منبعش را هم بگو" if language == "fa" else " include the source"
        return done
    except Exception:  # noqa: BLE001
        return None
