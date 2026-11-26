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


_SKIP_INTAKE = re.compile(
    r"فقط\s*معرفی|همین\s*الان|بدون\s*سوال|سوال\s*نپرس|(?:^|\s)معرفی\s*کن|(?:^|\s)(?:just (?:introduce|find|show)|skip|no questions)\b|فقط\s*رشح|بدون\s*أسئلة",
    re.I,
)


# a reminder / alarm request is its own flow, never an answer about the health episode (Codex P2, PR 198)
_OTHER_REQUEST = re.compile(r"یاد(?:م|ما|مان)?\s*(?:بنداز|بده|بنداز)|یادآور|یاد\s*آور|\bremind(?:er)?\b|\balarm\b|ذكرني|تذكير|منبه", re.I)


def _key(text: Optional[str]) -> str:
    return _NON_LETTERS.sub("", (text or "").lower())


PLACE_KEY = "care_nav.ask_place"
PLACE_CITY_KEY = "care_nav.ask_place_city"
_AFFIRM = re.compile(
    r"^\s*(?:بله|آره|اره|درسته|درست|صحیح|همین|همان|همون|همینه|yes|yeah|yep|correct|right|that'?s? (?:it|right)|نعم|صح)(?![\w])", re.I
)
_CITY_WORD = r"(?:شهر|شهرستان|city of|مدينة)\s*"


def place_status(text: str) -> tuple[str, "object"]:
    """('none' | 'ok' | 'confirm' | 'need_city', Place). R-106 (Javad 2026-11-19): a place is trusted ONLY when the user said it
    completely - area AND city, or a city the gazetteer verified, or «شهر X». Everything else (a neighbourhood that merely implies
    its city, a city without a verified directory slug such as «پردیس») is CONFIRMED with the user first."""
    place = cn._places.find_place(text or "")
    if not place.area and not place.city:
        return "none", place
    if place.area and not place.city:
        return "need_city", place
    explicit = bool(re.search(_CITY_WORD + re.escape(place.city), text or "", re.I))
    if place.area:
        return ("ok" if (not place.city_inferred or explicit) else "confirm"), place
    return ("ok" if (place.city_slug or explicit) else "confirm"), place


def _place_phrase(place, lang: str) -> str:
    area, city = place.area, place.city
    if area and city:
        if lang == "fa":
            return f"«{area}» در شهر {city}" if area.startswith("منطقه") else f"محلهٔ «{area}» در شهر {city}"
        if lang == "ar":
            return f"«{area}» في مدينة {city}"
        return f"“{area}” in {city}"
    return {"fa": f"شهر «{city}»", "ar": f"مدينة «{city}»", "en": f"the city of “{city}”"}[lang]


def place_question(message: str, language: str) -> Optional[str]:
    """The place question for a doctor/lab/centre request whose place is not yet confirmed, else None."""
    try:
        status, place = place_status(message)
        lang = language if language in ("fa", "ar", "en") else "en"
        if status == "confirm":
            return sedi_copy.t(PLACE_KEY, lang, place=_place_phrase(place, lang))
        if status == "need_city":
            return sedi_copy.t(PLACE_CITY_KEY, lang, area=place.area)
        return None
    except Exception:  # noqa: BLE001
        return None


def _contains_any(reply: Optional[str], key: str) -> bool:
    got = _key(reply)
    if not got:
        return False
    for lang in ("fa", "ar", "en"):
        for marker in sedi_copy.variants(key, lang):
            if _key(marker) and _key(marker) in got:
                return True
    return False


def place_already_known(message: str, rows: list, home: Optional[tuple] = None) -> Optional[str]:
    """R-120 (Javad 2026-11-26): a place the user ALREADY gave is never asked again. The place of ``message`` (an area whose city was only
    inferred, or a city without a directory slug) counts as known when (a) it is the user's stored residence (``home`` = (area, city) from
    the consent-gated CareState), (b) an earlier place question about it was answered «yes», or (c) the user himself named it WITH its city
    earlier. ``rows`` = recent turns, NEWEST FIRST, from the governed reader. Returns the confirmed place text for the request, else None."""
    try:
        status, place = place_status(message)
        if status != "confirm":
            return None
        area, city = place.area, place.city
        norm = lambda t: re.sub(r"[\s\u200c\-]+", "", str(t or ""))  # noqa: E731
        full = f"{area} {city}" if area else f"شهر {city}"
        if home and city and norm(home[1]) == norm(city) and (not area or norm(home[0]) == norm(area)):
            return full
        rows = list(rows or [])
        for i, r in enumerate(rows):
            said = str(getattr(r, "user_message", "") or "")
            got = cn._places.find_place(said)
            if area and got.area and norm(got.area) == norm(area) and got.city and norm(got.city) == norm(city) and not got.city_inferred:
                return full  # (c) he named it with its city himself
            reply = getattr(r, "sedi_response", None)
            if is_place_question(reply) and (not area or norm(area) in norm(reply)) and i > 0:
                answer = str(getattr(rows[i - 1], "user_message", "") or "")
                if _AFFIRM.match(answer.strip()):
                    return full  # (b) he confirmed it before
        return None
    except Exception:  # noqa: BLE001
        return None


def is_place_question(sedi_reply: Optional[str]) -> bool:
    return _contains_any(sedi_reply, "care_nav.markers.place") or _contains_any(sedi_reply, "care_nav.markers.place_city")


def first_question(message: str, language: str) -> Optional[str]:
    """R-105/R-106: the questions to ask FIRST, together in ONE message (up to three allowed): the reason / kind of doctor when the
    request names none, and the place when it is not confirmed. None when nothing is missing."""
    try:
        if not cn.is_care_navigation_query(message):
            return None
        parts = [q for q in (reason_question(message, language), place_question(message, language)) if q]
        return "\n\n".join(parts) or None
    except Exception:  # noqa: BLE001
        return None


def _confirmed_place_text(prior_request: str, answer: str, lang: str) -> Optional[str]:
    """The explicit, user-confirmed place for the completed request: a place the ANSWER names completely, or the prior place
    after a plain «yes». None = neither (the raw answer keeps its normal handling)."""
    named = cn._places.find_place(answer)
    if named.area and named.city and not named.city_inferred:
        return f"{named.area} {named.city}"
    if named.city and not named.area:
        return f"شهر {named.city}" if lang == "fa" else f"the city of {named.city}"
    if named.area:  # an area without its city: not confirmed - the next question asks about THIS place
        return named.area
    if _AFFIRM.match(answer):
        prior = cn._places.find_place(prior_request)
        if prior.area and prior.city:
            return f"{prior.area} {prior.city}"
        if prior.city:
            return f"شهر {prior.city}" if lang == "fa" else f"the city of {prior.city}"
    return None


def _swap_place(prior_request: str, place_text: str, lang: str) -> str:
    """The prior request with its (unconfirmed) place replaced by the confirmed one."""
    cleaned = cn._places.remove_places(prior_request)
    cleaned = re.sub(r"(?:\s|^)(?:در|in|في)\s*$", "", cleaned).strip()
    return f"{cleaned} در {place_text}" if lang == "fa" else f"{cleaned} in {place_text}"


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
        return bool(got) and any(_key(v) in got for lang in ("fa", "ar", "en") for v in sedi_copy.variants(ASK_KEY, lang))
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


_QUALIFIER_WORDS = {
    "24h": ("شبانه‌روزی", "open 24 hours"),
    "high_rating": ("با رضایت بالا", "highly rated"),
    "urgent": ("هرچه زودتر", "as soon as possible"),
}


def _with_qualifiers(request_text: str, quals: set, language: str) -> str:
    present = set(sl.qualifiers(request_text))
    for q in ("24h", "high_rating", "urgent"):
        if q in quals and q not in present:
            fa, en = _QUALIFIER_WORDS[q]
            request_text += " " + (fa if language == "fa" else en)
    return request_text


def _names_another_place(prior_request: str, answer: str) -> bool:
    """True when the ANSWER names a place different from the one being confirmed (a new, complete request)."""
    a, p = cn._places.find_place(answer), cn._places.find_place(prior_request)
    norm = cn._places.normalize
    return (norm(a.area or "") != norm(p.area or "")) or (norm(a.city or "") != norm(p.city or ""))


def request_for_answer(prior_request: Optional[str], sedi_reply: Optional[str], answer: str, language: str) -> Optional[str]:
    """The completed doctor request when ``answer`` replies to the reason question, else None (the message stays as it is)."""
    try:
        from backend.app.services.care_journey.journey import is_interview_reply

        asked_reason, asked_place = is_reason_question(sedi_reply), is_place_question(sedi_reply)
        asked_intake = is_interview_reply(sedi_reply)  # R-109: the grouped interview asked BEFORE the introduction
        if not prior_request or not answer or not (asked_reason or asked_place or asked_intake):
            return None
        text = answer.strip().replace(chr(0x200c), " ")  # half-space -> space so the patterns below see «نمی دونم»
        if not text or len(text.split()) > (80 if asked_intake else MAX_ANSWER_WORDS) or _NEVERMIND.search(text):
            return None
        if (
            cn.is_care_navigation_query(text)
            and sl.find_specialty(text)
            and cn._has_real_location(text)
            and (not asked_place or _names_another_place(prior_request, text))
        ):
            return None  # a complete doctor request of its own (kind AND place); while a place is pending it must name ANOTHER place
        lang3 = language if language in ("fa", "ar", "en") else "en"
        from backend.app.services.care_navigation import symptom_triage

        if symptom_triage.triage(text, language).red_flag:
            return None  # an emergency is never completed into a routine search, whatever else the answer says (Codex P1)
        urgent = symptom_triage.triage(text, language).urgency == "soon"
        if asked_intake and not asked_reason and not asked_place:  # the interview is answered: introduce NOW, tailored by what was said
            from backend.app.services.care_journey.journey import _answers_the_interview

            # only a message that ANSWERS the health interview (or says «just introduce») binds; a reminder or another request stays as it is
            # R-120: the interview now asks the REASON openly, so ANY answer binds (the pilot lost its city when «نه، فقط چکاپ» did not
            # match the old checklist patterns and the doctor search ran without a place); only another request stays as it is
            if _OTHER_REQUEST.search(text) or cn.is_care_navigation_query(text):
                return None
            quals = set(sl.qualifiers(prior_request)) | set(sl.qualifiers(text)) | ({"urgent"} if urgent else set())
            return _with_qualifiers(prior_request.strip(), quals, language)
        if asked_place and not asked_reason:  # only the place was asked: the specialty/entity is already in the prior request
            confirmed = _confirmed_place_text(prior_request, text, lang3)
            done_place = _swap_place(prior_request, confirmed, lang3) if confirmed else None
            if not done_place:
                return None
            # search preferences said WITH the confirmation («بله، شبانه‌روزی») survive (Codex P2, PR 194)
            quals = set(sl.qualifiers(prior_request)) | set(sl.qualifiers(text)) | ({"urgent"} if urgent else set())
            return _with_qualifiers(done_place, quals, language)
        spec = _specialty_for_answer(text, language)
        if spec is None and _DONT_KNOW.search(text):
            spec = "پزشک عمومی"
        if spec is None and asked_place:  # «بله» / «نه، شیراز»: the place is settled; the reason is asked next
            confirmed_only = _confirmed_place_text(prior_request, text, lang3)
            return _swap_place(prior_request, confirmed_only, lang3) if confirmed_only else None
        if spec is None:
            return None  # an emergency or something that names no specialty: normal handling
        place = (_confirmed_place_text(prior_request, text, lang3) if asked_place else None) or _place_in(text)
        if place:  # the answer named / confirmed a place: a fresh request with the specialty and THAT place
            done = f"یه دکتر {spec} در {place} معرفی کن" if language == "fa" else f"find a doctor {spec} in {place}"
        else:
            done = f"{prior_request.strip()} متخصص {spec}"
        if cn.wants_sources(text) and not cn.wants_sources(done):  # «neurology, include sources»: the source request survives (Codex P2)
            done += " منبعش را هم بگو" if language == "fa" else " include the source"
        quals = set(sl.qualifiers(prior_request)) | set(sl.qualifiers(text))
        if urgent:  # «high fever and cough»: the guidance «see a doctor within a day or two» must reach the reply (Codex P2)
            quals.add("urgent")
        done = _with_qualifiers(done, quals, language)  # preferences from BOTH turns survive (24h, high rating, urgent) - Codex P2
        return done
    except Exception:  # noqa: BLE001
        return None


def request_for_chain(rows: list, answer: str, language: str) -> Optional[str]:
    """The completed request when ``answer`` replies to the LAST question of this interview, however many partial answers came
    before («متخصص قلب» -> place question -> «بله»). ``rows`` are the recent turns NEWEST FIRST (user_message / sedi_response); the
    chain is the run of newest turns whose Sedi reply is one of this interview's questions (Codex P1, PR 194)."""
    try:
        chain = []
        for r in rows or []:
            reply = getattr(r, "sedi_response", None)
            from backend.app.services.care_journey.journey import is_interview_reply

            if is_reason_question(reply) or is_place_question(reply) or is_interview_reply(reply):
                chain.append(r)
            else:
                break
        if not chain:
            return None
        cur = getattr(chain[-1], "user_message", None)  # the original request (the oldest question's own turn)
        for i in range(len(chain) - 2, -1, -1):  # replay each earlier partial answer, oldest first
            said = getattr(chain[i], "user_message", "") or ""
            step = request_for_answer(cur, getattr(chain[i + 1], "sedi_response", None), said, language)
            # a standalone replacement request («یه دکتر پوست در کرمانشاه معرفی کن») starts a NEW chain root (Codex P2, PR 194)
            cur = step or (said if cn.is_care_navigation_query(said) and sl.find_specialty(said) else cur)
        return request_for_answer(cur, getattr(chain[0], "sedi_response", None), answer, language)
    except Exception:  # noqa: BLE001
        return None


def request_for_source_followup(prior_request: Optional[str], sedi_reply: Optional[str], message: str, language: str) -> Optional[str]:
    """«منبعش چیه؟» right after a provider list: the same request again, now asking for the source (the search is cached, so the same
    providers come back with their links and check dates) - Codex P2, PR 191. None when the last turn was not a doctor list."""
    try:
        if not prior_request or not cn.is_directory_source_question(message) or cn.is_care_navigation_query(message):
            return None
        if is_reason_question(sedi_reply) or not cn.is_care_navigation_query(prior_request):
            return None
        if cn.wants_sources(prior_request):
            return prior_request.strip()
        return prior_request.strip() + (" منبعش را هم بگو" if language == "fa" else " include the source")
    except Exception:  # noqa: BLE001
        return None
