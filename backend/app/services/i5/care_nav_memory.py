"""R-114 / R-115 (PR-A1, Javad 2026-11-21): the doctor request is completed FROM MEMORY, never by asking again what Sedi already knows.

Pilot chat (D-485): the user asked for a doctor; Sedi asked «برای چه مشکلی؟» five times and the city three times although the problem
(pain under the right ribs, one year) and the place (stored in I6) were known. Cause: ``care_nav_interview.reason_question`` and
``care_navigation_directory.parse_care_nav_request`` read only the CURRENT message.

This module is the ONE extension point for that: before the directory flow runs it turns an incomplete doctor request into the explicit
request the existing flow already understands («یه دکتر {تخصص} برام پیدا کن در {محل}»), using
  * the specialty the message / the user's stated problems (``CareState.issues``, consent-gated) / the recent turns point to,
  * the user's own stated residence (``CareState.home_area / home_city``) - used silently but NAMED in the answer so it can be corrected,
  * the user's insistence («تو باید پیدا کنی», «الکی سوال نکن», «شهرش مهم نیست») = proceed, never ask again.
Deterministic, no model, no schema; consent-gated through CareState; emergencies stay on the safety path; fail-open (None = the old flow).
Kill switch: ``SEDI_CARE_NAV_MEMORY_FIRST_ENABLED=false`` (unset = on).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from backend.app import sedi_copy
from backend.app.services.i5 import care_nav_interview as ci
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import specialty_lexicon as sl

logger = logging.getLogger(__name__)

FLAG = "SEDI_CARE_NAV_MEMORY_FIRST_ENABLED"  # default ON when unset; the flag workflow KILL_SWITCH writes «false» (R-113)
DEFAULT_CITY = {"fa": "تهران", "ar": "طهران", "en": "Tehran"}
_FALLBACK_SPECIALTY = "پزشک عمومی"

# --- the user's tone about it (any wording of the same intent, three languages) --------------------------------------------------------------------
_PROCEED = re.compile(
    r"(?:تو|شما)\s*(?:باید|بایستی)\s*(?:یه|یک)?\s*(?:دکتر|پزشک)?\s*(?:پیدا|معرفی)\s*(?:کنی|کنید)|باید\s*(?:پیدا|معرفی)\s*کنی|"
    r"(?:الکی|بی\s*خود|بیخود)\s*(?:سوال|سؤال)|(?:سوال|سؤال)(?:ی)?\s*(?:نکن|نپرس|نپرسید|نکنید)|دیگه\s*(?:سوال|سؤال)|بدون\s*(?:سوال|سؤال)|"
    r"فقط\s*(?:پیدا|معرفی|بده|بگو)|هر\s*چی\s*(?:میخوای|می\s*خوای|می\s*خواهی)\s*بده|چند\s*بار\s*(?:می)?پرس|"
    r"(?:مگه|مگر)\s*(?:قبلا|قبلاً|قبل)?\s*(?:بهت\s*)?(?:نگفتم|نگفته\s*بودم)|(?:قبلا|قبلاً|قبل\s*تر)\s*(?:گفتم|گفته\s*بودم)|گفتم\s*که|"
    r"لا\s*تسأل|بدون\s*أسئلة|كفى\s*أسئلة|سبق\s*(?:و)?قلت|قلت\s*لك|"
    r"\b(?:don.?t|do not|stop|no more)\s*(?:ask(?:ing)?|questions)|\bi (?:already )?(?:told|said)\b|\balready (?:told|said)\b|"
    r"\byou (?:have|need|must|should) (?:to )?find\b|\bjust (?:find|give|introduce)\b",
    re.I,
)
_ANY_PLACE = re.compile(
    r"(?:شهر(?:ش)?|جا(?:ش)?|محل(?:ش)?|مکان(?:ش)?)\s*(?:مهم|فرقی)\s*(?:نیست|نمی\s*کنه|نمیکنه|ندارد|نداره)|"
    r"هر\s*(?:جا(?:یی)?|شهر(?:ی)?|کجا(?:یی)?)|(?:شما|تو)\s*هر\s*جا\s*بگ|هر\s*کجا\s*که\s*(?:بگی|باشه)|"
    r"المدينة\s*غير\s*مهمة|أي\s*(?:مدينة|مكان)|"
    r"\bany\s*(?:city|place|where)\b|\b(?:city|place|location)\s*(?:doesn.?t|does not|isn.?t)\s*(?:matter|important)\b|\bwherever\b",
    re.I,
)
_REFERS = re.compile(
    r"(?:همون|همان|همین)(?:ی)?\s*(?:مشکل|درد|مورد|موضوع|مساله|مسئله)|(?:مشکل|درد)\s*(?:قبلی|بالا)|همون(?:ی)?\s*که\s*گفتم|"
    r"نفس\s*المشكلة|المشكلة\s*(?:نفسها|السابقة)|"
    r"\bthe\s*same\s*(?:problem|issue|pain|one)\b|\bsame\s*(?:problem|issue|pain)\b|\bas\s*i\s*(?:said|mentioned)\b",
    re.I,
)
_WS = re.compile(r"\s+")


def enabled() -> bool:
    raw = (os.getenv(FLAG) or "").strip().lower()
    return raw == "" or raw in ("1", "true", "yes", "on")


def _norm(text: Optional[str]) -> str:
    return _WS.sub(" ", (text or "").replace(chr(0x200C), " ")).strip()


def says_proceed(message: Optional[str]) -> bool:
    """The user insists / asks Sedi not to ask: «تو باید پیدا کنی», «الکی سوال نکن», «I already told you»."""
    return bool(_PROCEED.search(_norm(message)))


def says_any_place(message: Optional[str]) -> bool:
    """«شهرش مهم نیست», «هر جا», "any city"."""
    return bool(_ANY_PLACE.search(_norm(message)))


def refers_to_known(message: Optional[str]) -> bool:
    """«همون مشکل سمت راست بدنم», "the same problem": the answer points at what Sedi already knows."""
    return bool(_REFERS.search(_norm(message)))


@dataclass(frozen=True)
class MemoryRequest:
    text: str  # the explicit request for the directory flow
    notes: tuple[str, ...] = ()  # catalog lines shown before the answer (where the place came from, the other problem)
    reason_codes: tuple[str, ...] = ()
    tier_text: str = ""  # the ORIGINAL message + the complaint it was completed from: the care-journey urgency/area come from this, not from the rewritten query


def _lang3(language: Optional[str]) -> str:
    return language if language in ("fa", "ar", "en") else "en"


def _request_text(specialty: str, place: Optional[str], lang: str, qualifiers: set) -> str:
    if lang == "fa":
        text = f"یه دکتر {specialty} برام پیدا کن" + (f" در {place}" if place else "")
    elif lang == "ar":
        text = f"ابحث لي عن طبيب {specialty}" + (f" في {place}" if place else "")
    else:
        text = f"Please find me a doctor {specialty}" + (f" in {place}" if place else "")
    return ci._with_qualifiers(text, qualifiers, lang)


def _without_tone(message: str) -> str:
    """The message without the «I already told you / the same problem» wording: the triage treats «قبلا» as history and would skip the complaint."""
    return _WS.sub(" ", _REFERS.sub(" ", _PROCEED.sub(" ", _norm(message)))).strip()


def _spec_of(text: str, lang: str) -> Optional[str]:
    """The specialty a complaint text points to (triage; an emergency gives None so the safety path keeps it)."""
    try:
        return ci._specialty_for_answer(text, lang) if (text or "").strip() else None
    except Exception:  # noqa: BLE001
        return None


def _pending_question(rows: list, now: Any) -> bool:
    """Sedi's last reply (within 30 minutes) is a question of a DOCTOR conversation: the deterministic reason / place question, or a
    question the model wrote while a doctor request is part of the recent turns (the pilot chat's «در کدام شهر؟»)."""
    from datetime import timedelta

    last = rows[0] if rows else None
    if last is None or getattr(last, "created_at", None) is None:
        return False
    if now - last.created_at.replace(tzinfo=None) > timedelta(minutes=30):
        return False
    reply = getattr(last, "sedi_response", None) or ""
    if ci.is_reason_question(reply) or ci.is_place_question(reply):
        return True
    asks = "؟" in reply[-300:] or "?" in reply[-300:]
    return asks and any(cn.is_care_navigation_query(getattr(r, "user_message", None) or "") for r in rows)


# --- R-120 am.4 (Javad's phone test 2026-11-28): a SHORT follow-up of an open doctor conversation --------------------------------------------------
# Sedi opened with «last time we talked about finding the right doctor for you»; «معرفی کن برام» got her own introduction, «منظورم پزشک بود» a
# single old doctor from the free model, «برام چندتای دیگه معرفی کن» her introduction again. A message that only asks to introduce / find / show
# (or corrects «I meant a doctor») while the newest conversation is a doctor search is THAT search, completed from memory.
TOPIC_MAX_AGE_DAYS = 7
_MEANT_DOCTOR = re.compile(
    r"منظور(?:م|من)\s*(?:هم\s*)?(?:یه\s*|یک\s*)?(?:دکتر|پزشک|متخصص)|(?:دکتر|پزشک|متخصص)\s*(?:رو|را)?\s*(?:گفتم|می\s*گفتم|منظورم\s*بود)|"
    r"(?:أقصد|اقصد|قصدت|قصدي)\s*(?:ال)?(?:طبيب|دكتور|أطباء|اطباء)|"
    r"\bi\s+meant\s+(?:a\s+|the\s+)?(?:doctor|physician|specialist)s?\b|\bi\s+mean\s+(?:a\s+)?(?:doctor|physician|specialist)s?\b",
    re.I,
)
_ASK_VERB = re.compile(
    r"معرفی\s*(?:کن|کنی|بکن|کنید|بفرمایید)|پیدا\s*(?:کن|کنی|بکن|کنید)|(?:نشون|نشان)\s*(?:بده|بدی|بدهید)|بفرست|"
    r"(?:رشح|رشحي|اقترح|ابحث|اعرض|أرسل|ارسل)(?:\s*لي)?|"
    r"\b(?:introduce|find|show|recommend|suggest|send|give)\b",
    re.I,
)
# words that carry no subject of their own («برام», «چندتای دیگه», «لطفا», "me a few more") - anything else makes it a different request
_FILLER = frozenset(
    "برام برایم بهم به من یه یک یکی چند چندتا چندتای تا تای دیگه دیگر دیگری بیشتر بقیه رو را اونا اونها آنها همون همان همین پس خب خوب باشه "
    "حالا الان لطفا لطفاً لطفن دوباره هم و دکتر دکترها دکترای پزشک پزشکان پزشکها متخصص متخصصها اون آن ها "
    "لي من فضلك المزيد آخرين اخرين أخرى اخرى طبيب أطباء اطباء دكتور "
    "me a an one some few more other others another please again now then ok okay so them the doctor doctors specialist specialists".split()
)


def asks_doctor_ellipsis(message: Optional[str]) -> bool:
    """«معرفی کن برام», «برام چندتای دیگه معرفی کن», «منظورم پزشک بود», "find me some": a short request with no subject of its own."""
    text = _norm(message)
    if not text or len(text) > 60:
        return False
    if _MEANT_DOCTOR.search(text):
        return True
    if not _ASK_VERB.search(text):
        return False
    rest = _ASK_VERB.sub(" ", text)
    words = [w for w in re.findall(r"[^\W\d_]+", rest.lower()) if w]
    return all(w in _FILLER for w in words)


def doctor_topic_open(rows: list, now: Any) -> bool:
    """The newest meaningful turn (within ``TOPIC_MAX_AGE_DAYS``) belongs to a doctor search - the same turn the opener speaks about."""
    from datetime import timedelta

    from backend.app.services.care_journey import journey as _journey
    from backend.app.services.i7 import conversation_recap as _recap
    from backend.app.services.i7 import governed_raw

    for row in rows or []:
        created = getattr(row, "created_at", None)
        if created is not None and now - created.replace(tzinfo=None) > timedelta(days=TOPIC_MAX_AGE_DAYS):
            return False
        said = str(getattr(row, "user_message", "") or "")
        reply = str(getattr(row, "sedi_response", "") or "")
        if governed_raw.provider_intro_of_turn(row) is not None or _journey.is_interview_reply(reply) or _journey.is_followup_reply(reply):
            return True
        if ci.is_reason_question(reply) or ci.is_place_question(reply) or cn.is_care_navigation_query(said):
            return True
        if _recap.is_trivial_turn(said):
            continue  # «باشه», «ممنون» never decide the topic
        topic = _recap.classify_turn(said)
        if topic == "doctor":
            return True
        if topic is not None:
            return False  # a newer named subject (sleep, food, feelings…) closed the doctor talk
        # an unnamed answer inside the doctor talk («هیچ مشکلی ندارم») neither opens nor closes it: look one turn further back
    return False


def _next_five_pending(db: Any, user_id: int, message: str) -> bool:
    """«چندتای دیگه» with a previous introduction to continue: the next-five path owns it (memory would repeat the same five)."""
    try:
        from backend.app.services.i5 import provider_next as pn

        return pn.wants_next(message) and pn.latest_state(db, user_id) is not None
    except Exception:  # noqa: BLE001
        return False


def complete_request(db: Any, user_id: int, message: str, language: Optional[str], *, rows: Optional[list] = None) -> Optional[MemoryRequest]:
    """The memory-completed doctor request, or None (not a doctor request / nothing known / disabled / any doubt = the old flow)."""
    try:
        if not enabled() or db is None or not (message or "").strip():
            return None
        from datetime import datetime

        from backend.app.services.care_navigation import symptom_triage
        from backend.app.services.care_state import get_care_state

        lang = _lang3(language)
        rows = rows or []
        is_query = cn.is_care_navigation_query(message)
        proceed, any_place, refers = says_proceed(message), says_any_place(message), refers_to_known(message)
        now = datetime.utcnow()
        pending = _pending_question(rows[:4], now)
        # R-120 am.4: a short follow-up of the open doctor conversation (not when the next five of an introduction are asked for)
        ellipsis = (not is_query) and asks_doctor_ellipsis(message) and doctor_topic_open(rows, now) and not _next_five_pending(db, user_id, message)
        if not (is_query or ellipsis or (pending and (proceed or any_place or refers))):
            return None
        if symptom_triage.triage(message, lang).red_flag:
            return None  # an emergency is never completed into a routine search
        # the message that CARRIES the doctor request: this one, or - when it only answers Sedi's pending question - the earlier request
        base = message
        if not is_query:
            base = next((getattr(r, "user_message", "") or "" for r in rows if cn.is_care_navigation_query(getattr(r, "user_message", "") or "")), "")
            if not base:
                return None
            if symptom_triage.triage(base, lang).red_flag:
                return None
        req = cn.parse_care_nav_request(base, language=lang)
        if req.entity is not cn.CareNavEntity.SPECIALIST:
            return None  # labs, hospitals, pharmacies keep their own flow (also when the pending request was one)
        named = req.specialty_or_service or req.name_hint
        has_place = cn._has_real_location(base)
        if named and has_place and is_query:
            return None  # a complete request of its own

        state = get_care_state(db, user_id)
        known = state is not None and state.consent
        issues = list(state.issues) if known else []

        spec, used_issue, src_text = None, None, ""
        if named:
            spec = req.specialty_or_service  # already in the request (a doctor's NAME keeps the request text); only the place may be missing
        else:
            spec = _spec_of(_without_tone(message), lang) or _spec_of(base, lang)  # the CURRENT answer's symptoms first (Codex P2, PR 211 round 3)
            if spec is None:
                best = -1
                for issue in issues:  # the problem the message mentions wins; otherwise the primary (first) one
                    candidate = _spec_of(issue.text, lang)
                    if not candidate:
                        continue
                    overlap = sum(1 for w in set(re.findall(r"\w{3,}", issue.text)) if w in message)
                    if overlap > best:
                        best, spec, used_issue, src_text = overlap, candidate, issue, issue.text
            if spec is None and known:
                for row in rows:  # the recent user turns (the retention-eligible reader, consent-gated by the caller)
                    spec = _spec_of(getattr(row, "user_message", "") or "", lang)
                    if spec:
                        src_text = getattr(row, "user_message", "") or ""
                        break
            if spec is None and (proceed or any_place):
                spec = _FALLBACK_SPECIALTY  # the user insists: a general practitioner first, never the same question again
            if spec is None:
                return None  # nothing known and no insistence: the existing single question stays

        notes: list[str] = []
        codes = ["CARE_NAV_MEMORY_FIRST"]
        place = None
        if has_place:  # the user's own place of the request is kept (Codex P2, PR 211)
            place = " ".join(p for p in (req.area, req.city) if p) or None
        else:
            area, city = (state.home_area, state.home_city) if known else (None, None)
            if area or city:
                place = f"{area} {city}".strip() if (area and city) else (area or city)
                notes.append(sedi_copy.t("care_nav.memory.place_used", lang, place=place))
                codes.append("CARE_NAV_STORED_PLACE")
            elif any_place:
                place = DEFAULT_CITY[lang]
                notes.append(sedi_copy.t("care_nav.memory.place_default", lang, city=place))
                codes.append("CARE_NAV_DEFAULT_CITY")
        if proceed or any_place:
            codes.append("CARE_NAV_INSISTENCE_PROCEED")
        if ellipsis:
            codes.append("R120_DOCTOR_ELLIPSIS_BOUND")
        if spec and used_issue is not None:
            for other in issues:  # D3: a second problem gets its own specialty named, the search runs for the main one
                if other is used_issue:
                    continue
                other_spec = _spec_of(other.text, lang)
                if other_spec and other_spec != spec:
                    notes.append(sedi_copy.t("care_nav.memory.other_issue", lang, issue=other.text, specialty=other_spec))
                    break
        quals = set(sl.qualifiers(message)) | set(sl.qualifiers(base))
        if named and not spec:  # asked by a doctor's name: the original request text, plus the place
            if not place or has_place:
                return None
            text = f"{base.strip()} در {place}" if lang == "fa" else f"{base.strip()} in {place}"
        elif named and is_query and not has_place:  # specialty named, place completed from memory: the user's own wording plus the place
            if not place:
                return None
            text = f"{message.strip()} در {place}" if lang == "fa" else f"{message.strip()} in {place}"
        else:
            text = _request_text(spec, place, lang, quals)
        if (cn.wants_sources(message) or cn.wants_sources(base)) and not cn.wants_sources(text):  # a requested source survives (Codex P2, PR 211)
            text += " منبعش را هم بگو" if lang == "fa" else " include the source"
        tier_text = " ".join(x for x in (message, base if base != message else "", src_text) if x).strip()
        return MemoryRequest(text=text, notes=tuple(notes), reason_codes=tuple(codes), tier_text=tier_text)
    except Exception:  # noqa: BLE001
        logger.exception("[R-114] memory-first doctor request skipped")
        return None
