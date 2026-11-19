"""R-088 / R-091 (D-382..D-387), package A1 v2: a pill reminder asked for IN CHAT becomes a short CARE INTERVIEW and only then
goes to the MEDICATION OWNER.

Before: «هر روز ساعت ۲ یادم بنداز قرص بخورم» created a generic UserEvent at once - Sedi never knew the medicine or the user's
situation, and the pill notification was a fixed «Time to take X».

Now (recurring pill reminders; Javad D-386 / D-387): the time is NOT set first. Sedi first learns the exact name of the
medicine (spelling / a photo of the box when unsure), then the reason for taking it, and only then creates the reminder
through ``user_medication_service`` (single owner, R-005) at the stated time, in harmony with what she learned.

Escapes - the request is never lost:
* the user insists («همین ساعت», «فقط یادم بنداز») or gives a non-answer -> create it at once with the stated time and say that
  Sedi keeps caring for the user's health and is open to talk about it;
* no consent / no conversation memory (the interview state lives in the consent-gated conversation) -> create it at once and ask
  which pill (the A1 v1 behaviour).

The interview state is DERIVED from the conversation (Sedi's last reply carries the stage marker, the original request is
re-read from the recent turns): no new table. Medicine introduction via online search = package A2; varied pill notifications
with a care suggestion = package A4.

Fail-open: any error returns ``None`` and the caller keeps the old UserEvent path. Kill switch (code default ON, no env change):
SEDI_MEDICATION_CHAT_OWNER_DISABLED=1.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models, sedi_copy

logger = logging.getLogger(__name__)

DISABLED_ENV = "SEDI_MEDICATION_CHAT_OWNER_DISABLED"
PROVISIONAL_KEY = "medication.chat.provisional_name"
BIND_WINDOW = timedelta(hours=6)
MAX_ANSWER_WORDS = 6
STAGE_KEYS = {  # order matters: «unrecognised» also contains the confirm-name question, so it is tested first
    "ask_name": "medication.chat.markers.ask_name",
    "unrecognised": "medication.chat.markers.unrecognised",
    "confirm_name": "medication.chat.markers.confirm_name",
    "ask_reason": "medication.chat.markers.ask_reason",
}

_ARABIC_MARKS = re.compile("[ً-ٰٟـ‌‏‎]")
_FOLD = (("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("ة", "ه"))

# Medicine words (fa / ar / en) with common Persian/Arabic clitics. «داروخانه» / pharmacy is a place, not a medicine.
_MED_WORD = re.compile(
    r"(?<![؀-ۿA-Za-z])[بلو]?(?:قرص|کپسول|آمپول|شربت|قطره|دارو|ویتامین|مکمل|حبوب|دوائ|دواء|ادویه|أدویه|كبسولة|كبسول|"
    r"pills?|tablets?|capsules?|medicines?|medications?|vitamins?|supplements?|meds?)"
    r"(?:ها|های|هام|ام|م|ت|ش|ی|ي|ه|ك|نا|مو)?"
    r"(?![؀-ۿA-Za-z])",
    re.I,
)
_PHARMACY = re.compile(r"داروخانه|داروساز|pharmac|صيدلي", re.I)
# Codex P2 (PR 185): «every day at 9pm remind me to BUY pills» is an errand, not an intake schedule. An errand word
# (buy / refill / count / order / renew) keeps the generic event route UNLESS an intake word is also present.
_ERRAND = re.compile(
    r"بخر|خرید|تمدید|بشمار|شمارش|سفارش|buy|purchase|pick\s*up|refill|re-?order|order\b|count|renew|اشتري|شراء|تجديد|اطلب",
    re.I,
)
_INTAKE = re.compile(
    r"بخور|خوردن|مصرف|\btake\b|\btaking\b|\bintake\b|\bdrink|تناول|آخذ|أخذ|اشرب|اخذ",
    re.I,
)

# «داروی فشارم» names a condition, not a medicine: only product-type words introduce a name.
_NAME_AFTER = re.compile(
    r"(?:قرص|کپسول|آمپول|شربت|قطره|ویتامین|مکمل)\s+([A-Za-z؀-ۿ][A-Za-z0-9؀-ۿ\-]{1,30})"
    r"(?:\s+([0-9۰-۹]{1,4}\s*(?:mg|mcg|میلی‌?گرم|میکروگرم|iu|واحد)))?",
    re.I,
)
_NAME_BEFORE_EN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9\-]{2,30})\s+(?:pills?|tablets?|capsules?)\b|\btake\s+(?:my\s+)?([A-Za-z][A-Za-z0-9\-]{2,30})\b",
    re.I,
)
_STOP = frozenset(
    "را رو های هام م ام مو بخورم بخورد بخور بخوری مصرف مصرفی هر روز ساعت صبح ظهر عصر شب یادم یادمه بنداز بندازی بهم "
    "من خودم لطفا لطفاً کن کنی بزن بگو بفرست نوتیف یک یه دو سه چهار بعد قبل از بعدازظهر نیمه وعده تا است هست باید "
    "the my a an to at every day daily morning evening night noon please remind me take pill pills tablet tablets capsule "
    "capsules medicine medicines medication medications vitamin vitamins supplement supplements meds med".split()
)
_YES = re.compile(r"^(?:بله|آره|اره|ایول|درسته|درست|همینه|همین|صحیح|اوهوم|yes|yeah|yep|correct|right|نعم|صحيح|أجل)\b", re.I)
_NO = re.compile(r"^(?:نه|نخیر|خیر|no|nope|لا)\b", re.I)
_INSIST = re.compile(
    r"(?:همین\s+ساعت|فقط\s+(?:یادم\s+بنداز|یادآوری|یادآور)|بدون\s+(?:سوال|سؤال|پرسش)|سوال\s+نپرس|"
    r"just\s+remind|no\s+questions|same\s+time|without\s+questions|فقط\s+ذكرني|بدون\s+أسئلة)",
    re.I,
)
_NON_ANSWER = re.compile(
    r"^(?:نمی\s*?دونم|نمی\s*?دانم|فرقی\s+نمی\s*?کنه|مهم\s+نیست|بی\s*?خیال|نمی\s*?خوام|نمیخوام|i\s+don'?t\s+know|skip|never\s+mind|"
    r"لا\s+أعرف|لا\s+أريد)",
    re.I,
)
_QUOTED = re.compile("[«\"“]([^»\"”]{2,120})[»\"”]")
_BYDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _fold(text: str) -> str:
    out = text or ""
    for a, b in _FOLD:
        out = out.replace(a, b)
    return _ARABIC_MARKS.sub("", out)


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def _lang(language: Optional[str]) -> str:
    return language if language in ("fa", "ar", "en") else "en"


def provisional_name(language: Optional[str]) -> str:
    return sedi_copy.t(PROVISIONAL_KEY, _lang(language))


def is_medication_text(text: str) -> bool:
    folded = _fold(text)
    if not _MED_WORD.search(folded) or _PHARMACY.search(folded):
        return False
    return not (_ERRAND.search(folded) and not _INTAKE.search(folded))


def insists(text: str) -> bool:
    return bool(_INSIST.search(_fold(text)))


def extract_pill_name(text: str) -> Optional[str]:
    """A medicine name written right after «قرص/کپسول/…» (or «X pill»). None when uncertain - the user is then asked."""
    folded = _fold(text)
    for m in _NAME_AFTER.finditer(folded):
        word = m.group(1).strip("-")
        if word.lower() in _STOP or word in _STOP or len(word) < 3:
            continue
        dose = m.group(2)
        return (word + (" " + dose.strip() if dose else ""))[:120]
    for m in _NAME_BEFORE_EN.finditer(folded):
        word = (m.group(1) or m.group(2) or "").strip("-")
        if word and word.lower() not in _STOP and len(word) >= 3:
            return word[:120]
    return None


def _hhmm(draft: Any) -> Optional[str]:
    start = getattr(draft, "starts_at_local", None)
    return start.strftime("%H:%M") if isinstance(start, datetime) else None


def fire_times(draft: Any) -> Optional[list[str]]:
    """The dose time for the medication schedule, or None when the medication route cannot represent the request.

    The schedule time IS the dose time (the dose occurrence and the adherence record are created at that time), and the
    medication schedule has no «advance reminder» field. A request with an EXPLICIT offset («نیم‌ساعت قبل», "30 minutes
    before") therefore keeps the generic event route, which stores the offset correctly (Codex P2 x2, PR 185). The parser's
    DEFAULT offset (added when the user used no reminder word) is ignored: a pill is taken AT the time.
    """
    start = getattr(draft, "starts_at_local", None)
    if not isinstance(start, datetime):
        return None
    if not getattr(draft, "offsets_defaulted", False) and any(int(o or 0) for o in (getattr(draft, "reminder_offsets", None) or ())):
        return None
    return [f"{start.hour:02d}:{start.minute:02d}"]


def _days_of_week(rule: Optional[str]) -> Optional[str]:
    """«FREQ=WEEKLY;BYDAY=MO,TH» -> «0,3» (Monday = 0); daily -> None (every day)."""
    m = re.search(r"BYDAY=([A-Z,]+)", rule or "")
    if not m:
        return None
    days = sorted({_BYDAY[d] for d in m.group(1).split(",") if d in _BYDAY})
    return ",".join(str(d) for d in days) or None


def _is_recurring(rule: Optional[str]) -> bool:
    return bool(rule) and ("FREQ=DAILY" in rule or "FREQ=WEEKLY" in rule)


def has_future_start(draft: Any, now_utc: Optional[datetime] = None) -> bool:
    """True when the request names a start DAY later than the next time the clock time occurs («از فردا ساعت ۹ شب» asked in the
    afternoon). The medication schedule has no start date and would fire a day early, so such a request keeps the generic
    event route, which knows its date (Codex P2, PR 185). Fail-closed: any doubt -> True (keep the generic route)."""
    try:
        import pytz

        start = getattr(draft, "starts_at_local", None)
        if not isinstance(start, datetime):
            return True
        zone = pytz.timezone(getattr(draft, "timezone_name", None) or "UTC")
        moment = (now_utc or datetime.now(timezone.utc))
        local_now = (moment if moment.tzinfo else moment.replace(tzinfo=pytz.UTC)).astimezone(zone).replace(tzinfo=None)
        next_occurrence = local_now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
        if next_occurrence <= local_now:
            next_occurrence += timedelta(days=1)
        return start.date() > next_occurrence.date()
    except Exception:  # noqa: BLE001
        return True


def history_available(db: Session, user_id: int) -> bool:
    """The interview state lives in the consent-gated conversation memory (R-021): it must be both WRITTEN (the question) and
    READ back (the answer). Read-only consent cannot hold the state -> immediate-creation fallback (Codex P2, PR 185)."""
    try:
        from backend.app.services.i6.consent_service import PERM_READ, PERM_WRITE, has_permission

        return bool(has_permission(db, user_id, PERM_READ) and has_permission(db, user_id, PERM_WRITE))
    except Exception:  # noqa: BLE001
        return False


def _create(
    db: Session, *, user_id: int, draft: Any, language: Optional[str], timezone_name: Optional[str], name: Optional[str]
) -> Optional[dict[str, Any]]:
    """The ONLY medication-owner write of this flow. ``name`` None -> provisional name (A4 keeps asking later)."""
    try:
        from backend.app.schemas.medical import UserMedicationCreateIn
        from backend.app.services import user_medication_service as svc

        times = fire_times(draft)
        if not times:
            return None
        hhmm = times[0]
        use_name = name or provisional_name(language)
        try:
            out = svc.create_user_medication(
                db, user_id, UserMedicationCreateIn(name=use_name, reminder_times=times, timezone=timezone_name or None)
            )
        except svc.DuplicateUserMedicationError:
            return {"kind": "medication", "created": False, "duplicate": True, "name": use_name, "named": bool(name), "time": hhmm}
        days = _days_of_week(getattr(draft, "recurrence_rule", None))
        if days:
            um = db.query(models.UserMedication).filter(models.UserMedication.id == out["id"]).first()
            if um is not None:
                for row in um.schedules:
                    row.days_of_week = days
                db.commit()
        return {
            "kind": "medication", "created": True, "duplicate": False, "user_medication_id": out.get("id"),
            "name": use_name, "named": bool(name), "time": hhmm, "days": days,
        }
    except Exception:  # noqa: BLE001 - chat must never break
        logger.exception("[R-088] medication owner create failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


# --- turn 1: the request ------------------------------------------------------------------------------------------
def start_interview(
    db: Session, *, user_id: int, message: str, draft: Any, language: Optional[str], timezone_name: Optional[str]
) -> Optional[dict[str, Any]]:
    """First turn of a recurring pill request. None = not applicable (the generic UserEvent path stays)."""
    try:
        if not enabled() or not is_medication_text(message) or not _is_recurring(getattr(draft, "recurrence_rule", None)):
            return None
        if not _hhmm(draft) or has_future_start(draft) or fire_times(draft) is None:
            return None
        found = extract_pill_name(message)
        flow = None
        if insists(message):
            flow = "insist"
        elif not history_available(db, user_id):
            flow = "no_history"
        if flow:
            out = _create(db, user_id=user_id, draft=draft, language=language, timezone_name=timezone_name, name=found)
            if out is not None:
                out["flow"] = flow
            return out
        return {
            "kind": "medication", "created": False, "interview": "confirm_name" if found else "ask_name",
            "name": found or "", "named": bool(found), "time": (fire_times(draft) or [_hhmm(draft)])[0], "reason": "interview",
        }
    except Exception:  # noqa: BLE001
        logger.exception("[R-088] medication interview start failed")
        return None


def confirmation(dispatched: dict[str, Any], language: Optional[str], when: str) -> str:
    """Sedi's text for a medication dispatch result: the next interview question, or the created reminder."""
    lang = _lang(language)
    stage = dispatched.get("interview")
    if stage == "confirm_name":
        return sedi_copy.t("medication.chat.q.confirm_name", lang, name=dispatched.get("name", ""))
    if stage == "ask_name":
        return sedi_copy.t("medication.chat.q.ask_name", lang)
    if dispatched.get("flow") == "insist":
        key = "medication.chat.created.insist_named" if dispatched.get("named") else "medication.chat.created.insist_unnamed"
        return sedi_copy.t(key, lang, name=dispatched.get("name", ""), time=dispatched.get("time", ""))
    # no-history fallback: the reminder exists, ask which pill
    if dispatched.get("named"):
        return sedi_copy.t("medication.chat.confirm_named", lang, name=dispatched.get("name", ""), when=when)
    return sedi_copy.t("medication.chat.confirm_unnamed", lang, when=when)


# --- the next turns: continuing the interview from the conversation ------------------------------------------------
def _candidate_name(message: str) -> Optional[str]:
    text = _fold(message).strip().strip("«»\"'.؟?!،, ")
    if not text or len(text.split()) > MAX_ANSWER_WORDS or _YES.match(text) or _NO.match(text):
        return None
    cleaned = re.sub(r"^(?:اسمش|اسم\s*آن|نامش|اسم|نام|قرص|داروی|دارو|کپسول|its|it is|it's|called|name is)\s+", "", text, flags=re.I)
    cleaned = re.sub(r"\s+(?:است|هست|ه|می‌باشد)$", "", cleaned).strip()
    if not cleaned:
        return None
    # Codex P1 (PR 185): only the leading medicine NAME is ever kept (it is stored in the catalog and sent to the lookup);
    # «Metformin for my diabetes» -> «Metformin»; a reply that is a sentence / health detail / phone number -> None.
    from backend.app.services.medication_care.drug_brief import name_from_reply

    return name_from_reply(cleaned)


def _is_new_reminder_request(message: str, language: Optional[str], timezone_name: Optional[str]) -> bool:
    """A message with reminder words AND a complete time is a request of its own, not an answer to the interview."""
    try:
        from backend.app.services.intelligence.reminder_event_readiness import _REMINDER_WORDS, parse_reminder_event_draft

        if not _REMINDER_WORDS.search(_fold(message)):
            return False
        draft, missing = parse_reminder_event_draft(message=message, timezone_name=timezone_name or "UTC", language=language)
        return draft is not None and missing is None
    except Exception:  # noqa: BLE001
        return False


def _recent_turns(db: Session, user_id: int, now: datetime) -> list[Any]:
    try:
        from backend.app.services.i7.retention import query_eligible_raw

        since = now.replace(tzinfo=None) - BIND_WINDOW
        return [t for t in query_eligible_raw(db, user_id, limit=12) if t.created_at is not None and t.created_at >= since]
    except Exception:  # noqa: BLE001
        return []


def _reason_reply(name: str, lang: str, *, introduce: bool = True) -> str:
    """The reason question, preceded (A2) by Sedi's introduction of the medicine from the web: what it is used for, the sites and
    the date, plus the offer to accompany the user. Not recognised -> ask for the exact name / a photo of the box (never a
    guess). No result / error / kill switch -> the plain reason question (fail-open)."""
    if introduce:
        try:
            from backend.app.services.medication_care import drug_brief

            brief = drug_brief.lookup(name, lang)
            if brief is not None:
                if not brief.recognized:
                    return sedi_copy.t("medication.chat.q.unrecognised", lang, name=name)
                intro = drug_brief.compose(brief, name, lang)
                return intro + chr(10) + sedi_copy.t("medication.chat.q.ask_reason_after_brief", lang)
        except Exception:  # noqa: BLE001
            pass
    return sedi_copy.t("medication.chat.q.ask_reason", lang, name=name)


def _stage_of(reply: Optional[str], language: Optional[str]) -> Optional[str]:
    text = _fold(reply or "").lower()
    lang = _lang(language)
    for stage, key in STAGE_KEYS.items():
        if any(_fold(m).lower() in text for m in sedi_copy.variants(key, lang, "fa")):
            return stage
    return None


def _request_candidates(turns: list[Any]) -> list[tuple[str, Any]]:
    """Texts that may hold the original request, newest first: a turn's own message, and that message completed by the
    clarification answer the user gave to Sedi's «morning or evening?» / «when?» question (Codex P2, PR 185)."""
    from backend.app.services.intelligence.reminder_event_readiness import is_period_clarification, is_reminder_clarification

    out: list[tuple[str, Any]] = []
    for i, t in enumerate(turns):  # newest first
        out.append((str(getattr(t, "user_message", "") or ""), t))
        older = turns[i + 1] if i + 1 < len(turns) else None
        if older is not None:
            asked = getattr(older, "sedi_response", None)
            if is_period_clarification(asked) or is_reminder_clarification(asked):
                prior = str(getattr(older, "user_message", "") or "").strip()
                answer = str(getattr(t, "user_message", "") or "").strip()
                if prior and answer:
                    out.append((prior + " " + answer, older))
    return out


def _original_request(turns: list[Any], language: Optional[str], timezone_name: Optional[str]) -> Optional[tuple[Any]]:
    from backend.app.services.intelligence.reminder_event_readiness import parse_reminder_event_draft

    for text, t in _request_candidates(turns):
        if not is_medication_text(text):
            continue
        draft, missing = parse_reminder_event_draft(
            message=text, timezone_name=timezone_name or "UTC", now_utc=t.created_at, language=language
        )
        if draft is not None and missing is None and _is_recurring(draft.recurrence_rule) and fire_times(draft) is not None and not has_future_start(draft, t.created_at):
            return (draft,)
    return None


def _accompany(db: Session, user_id: int, lang: str, name: str, reason_message: str) -> bool:
    """A3 (R-088 am.2 / R-051 / R-068): after the user told WHY the medicine is taken, Sedi's companionship becomes ONE tracked
    commitment in the existing I10 loop (next local day 09:00, then every <=2 days, a new approach each time; the lock-screen
    text of that loop never names an illness). The gate (memory-write consent, severe-symptom floor, fail-open) lives in
    ``commitment_followup.capture_step``. True only when the commitment really exists, so the promise in the reply is honest."""
    try:
        from backend.app.services.i10.commitment_followup import capture_step

        step = sedi_copy.t("medication.chat.commitment_step", lang, name=name)
        if capture_step(db, user_id, step, user_message=reason_message) is None:
            return False
        db.commit()
        return True
    except Exception:  # noqa: BLE001 - chat must never break
        logger.exception("[R-088] medication companionship commitment skipped")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def continue_interview(
    db: Session, *, user_id: int, message: str, language: Optional[str], timezone_name: Optional[str],
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Next step of the interview, or None when the message is not part of it (the normal flow handles it)."""
    try:
        if not enabled():
            return None
        # P1 (Codex, PR 185): revoked / expired memory-read consent must stop the use of the retained conversation at once
        if not history_available(db, user_id):
            return None
        turns = _recent_turns(db, user_id, now or datetime.now(timezone.utc))
        last = next((str(t.sedi_response) for t in turns if getattr(t, "sedi_response", None)), "")
        stage = _stage_of(last, language)
        if stage is None:
            return None
        lang = _lang(language)
        original = _original_request(turns, language, timezone_name)
        if original is None:
            return None
        draft = original[0]
        quoted = _QUOTED.search(last)
        name = quoted.group(1).strip() if quoted else None
        text = _fold(message).strip()

        def finish(final_name: Optional[str], key_named: str, key_unnamed: str, *, accompany: bool = False) -> Optional[str]:
            out = _create(db, user_id=user_id, draft=draft, language=lang, timezone_name=timezone_name, name=final_name)
            if out is None:
                return None
            if out.get("duplicate"):
                return sedi_copy.t("medication.chat.already_tracked", lang, name=out.get("name", ""))
            text = sedi_copy.t(key_named if final_name else key_unnamed, lang, name=out.get("name", ""), time=out.get("time", ""))
            if accompany and _accompany(db, user_id, lang, out.get("name", ""), message):
                text = text + " " + sedi_copy.t("medication.chat.created.followup_promise", lang)
            return text

        # a non-answer / insistence ends the interview now: the request is never lost
        if insists(message) or _NON_ANSWER.match(text):
            return finish(name, "medication.chat.created.insist_named", "medication.chat.created.insist_unnamed")
        # an INDEPENDENT reminder request («فردا ساعت ۱۰ جلسه را یادم بنداز») is never taken as an interview answer: it keeps its
        # normal routing, otherwise it would be swallowed and lost (Codex P2, PR 185)
        if _is_new_reminder_request(message, lang, timezone_name):
            return None
        # «unrecognised»: Sedi asked for the correct name, so a short reply there is that correction (Codex P2, PR 185)
        answer = _candidate_name(message) if stage in ("ask_name", "confirm_name", "unrecognised") else None
        if stage == "ask_name":
            return _reason_reply(answer, lang) if answer else None
        if stage in ("confirm_name", "unrecognised"):
            # «yes» to the unrecognised-name question confirms what is on the box: no second search for the same name
            if _YES.match(text) and name:
                return _reason_reply(name, lang, introduce=(stage == "confirm_name"))
            if _NO.match(text):
                return sedi_copy.t("medication.chat.q.ask_name", lang)
            return _reason_reply(answer, lang) if answer else None
        if stage == "ask_reason":
            if not text or len(text.split()) > 40:  # a long message is another topic: the normal flow answers it
                return None
            return finish(
                name, "medication.chat.created.after_reason", "medication.chat.created.after_reason_unnamed", accompany=True
            )
        return None
    except Exception:  # noqa: BLE001
        logger.exception("[R-088] medication interview continue failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
