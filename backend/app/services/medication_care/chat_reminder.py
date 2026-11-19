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
    "ask_reason_promoted": "medication.chat.markers.ask_reason_promoted",
    "ask_repeat": "medication.chat.markers.ask_repeat",
    "ask_same": "medication.chat.markers.ask_same",
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
# Codex P2 (PR 185): an explicit WITHDRAWAL of the request at any interview stage ends it with NO reminder and NO commitment
# (a bare «نمی‌خوام» / «skip» stays a non-answer = the request is kept). Only wording that names the reminder/cancelling counts.
_CANCEL = re.compile(
    # an IMPERATIVE / explicit withdrawal of THIS reminder only: «my surgery was cancelled» / «عملم لغو شد» / «تم إلغاء العملية» are
    # reasons for taking the medicine, not a withdrawal (Codex P2 round 5). The text is folded first (ي->ی, ك->ک).
    r"(?:^\s*(?:please\s+)?cancel(?:\s+(?:it|this|that|the\s+reminder|my\s+reminder|the\s+request))?[\s.!]*$|"
    r"\bcancel\s+(?:it|this|that|the\s+reminder|my\s+reminder|the\s+request)\b|"
    r"\bdon'?t\s+(?:set|create|make|add)\b|\bdo\s+not\s+(?:set|create|make|add)\b|\bno\s+reminders?\b|"
    r"\b(?:don'?t|do\s+not)\s+want\s+(?:a\s+|any\s+)?reminders?\b|"
    r"^\s*(?:لغو|کنسل)(?:ش|اش)?(?:\s+(?:کن|کنید|کنین|بکن|بکنید))?[\s.!]*$|(?:لغو|کنسل)(?:ش|اش)?\s+(?:کن|کنید|کنین|بکن|بکنید)\b|"
    r"(?:لغو|کنسل)\s+(?:این\s+)?(?:یادآور\w*|یادآوری)|نگذار|نذار|نزار|"
    r"(?:یادآور\w*|یادآوری|یادم\s+بنداز)\s+(?:رو\s+|را\s+)?(?:نمی\s*?خوام|نمیخوام|نمی\s*?خواهم|نه)\b|"
    r"(?:نمی\s*?خوام|نمیخوام|نمی\s*?خواهم)\s+(?:یادآور\w*|یادآوری)|"
    r"^\s*(?:إلغاء|الغاء)(?:\s+(?:ال)?تذ[كک][يی]ر)?[\s.!]*$|(?:ألغ|الغ)[يیِ]?(?:ه|ها)?\s+(?:ال)?تذ[كک][يی]ر|"
    r"لا\s+(?:تضع|تنشئ|تسجّل|تسجل)|لا\s+أر[يی]د\s+(?:تذ[كک][يی]ر|تنب[يی]ه))",
    re.I,
)
# R-103 step B: the answer to «just once, or repeat every day?»
_ONCE = re.compile(r"(?:یک\s*بار|فقط\s+(?:همین|فردا|امروز|این)|\bonce\b|\bjust\s+once\b|\bone\s*time\b|\bonly\s+once\b|مرة\s+واحدة|مره\s+واحده)", re.I)
_EVERY = re.compile(r"(?:هر\s*روز|روزانه|تکرار|همیشه|\bevery\s*day\b|\bdaily\b|\brepeat|[كک]ل\s+[يی]وم|[يی]وم[يی]|[يی]ت[كک]رر)", re.I)
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
def _same_action(db: Session, *, user_id: int, pill: dict[str, Any], draft: Any, lang: str) -> Optional[dict[str, Any]]:
    """The user's request is another dose of a pill that already exists: add the dose (registered pill) or PROMOTE the older
    reminder into the medicine owner (R-103 step B). None -> the caller continues with the ordinary interview."""
    try:
        from backend.app.services import user_medication_service as svc
        from backend.app.services.medication_care import pill_registry as reg

        time_ = (fire_times(draft) or [_hhmm(draft)])[0]
        days = _days_of_week(getattr(draft, "recurrence_rule", None))
        try:
            if pill["kind"] == "med":
                times = reg.add_dose(db, user_id, pill, time_, days, getattr(draft, "timezone_name", None))
                return {"kind": "medication", "created": True, "flow": "dose_added", "name": pill["name"], "time": time_,
                        "times": reg.times_text(times, lang)}
            times = reg.promote(db, user_id, pill, time_, days, getattr(draft, "timezone_name", None))
        except svc.ScheduleTimeCollisionError:
            return {"kind": "medication", "created": False, "flow": "dose_exists", "name": pill["name"], "time": time_}
        out: dict[str, Any] = {"kind": "medication", "name": pill["name"], "time": time_, "times": reg.times_text(times, lang)}
        if history_available(db, user_id):  # the reason is asked next (the older reminder never had one)
            out.update({"created": False, "interview": "ask_reason_promoted"})
        else:
            out.update({"created": True, "flow": "promoted"})
        return out
    except Exception:  # noqa: BLE001
        logger.exception("[R-103] same-pill action failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def _begin(
    db: Session, *, user_id: int, message: str, draft: Any, language: Optional[str], timezone_name: Optional[str]
) -> Optional[dict[str, Any]]:
    """A pill request that is (or has just been confirmed as) a DAILY series: another dose of a pill the user already has, or
    the care interview of a new one. None = the generic event path stays."""
    from backend.app.services.medication_care import pill_registry as reg

    lang = _lang(language)
    if not _hhmm(draft) or has_future_start(draft) or fire_times(draft) is None:
        return None
    found = extract_pill_name(message)
    try:
        pills = reg.existing_pills(db, user_id)
    except Exception:  # noqa: BLE001 - fail-open: no registry -> the ordinary interview
        pills = []
    hit = reg.match(found, pills)
    if hit is not None:  # «ساعت ۹ صبح هم قرص مکمل»: the name says it is the same pill
        res = _same_action(db, user_id=user_id, pill=hit, draft=draft, lang=lang)
        if res is not None:
            return res
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
    time_ = (fire_times(draft) or [_hhmm(draft)])[0]
    if pills and not found:  # no name given and the user has pills: «the same pill or a new one?»
        return {"kind": "medication", "created": False, "interview": "ask_same", "names": reg.names_text(pills, lang),
                "name": "", "named": False, "time": time_, "reason": "interview"}
    return {
        "kind": "medication", "created": False, "interview": "confirm_name" if found else "ask_name",
        "name": found or "", "named": bool(found), "time": time_, "reason": "interview",
    }


def start_interview(
    db: Session, *, user_id: int, message: str, draft: Any, language: Optional[str], timezone_name: Optional[str]
) -> Optional[dict[str, Any]]:
    """First turn of a pill request. None = not applicable (the generic UserEvent path stays).
    Recurring -> the care interview. No day word («ساعت ۹ صبح هم …») -> a DAILY series (Javad 2026-11-19). A day word («فردا ساعت
    ۹») -> Sedi ASKS «just once, or repeating?» before anything is created (R-103 am.2)."""
    try:
        if not enabled() or not is_medication_text(message) or not _hhmm(draft):
            return None
        from backend.app.services.medication_care import pill_registry as reg

        if not _is_recurring(getattr(draft, "recurrence_rule", None)):
            if reg.has_day_word(message, getattr(draft, "timezone_name", None) or timezone_name, None):
                if insists(message) or not history_available(db, user_id) or fire_times(draft) is None:
                    return None  # no place to keep the question: the plain event, as before
                return {"kind": "medication", "created": False, "interview": "ask_repeat", "name": "", "named": False,
                        "time": (fire_times(draft) or [_hhmm(draft)])[0], "reason": "interview"}
            draft = reg.as_daily(draft)
        return _begin(db, user_id=user_id, message=message, draft=draft, language=language, timezone_name=timezone_name)
    except Exception:  # noqa: BLE001
        logger.exception("[R-088] medication interview start failed")
        return None


def confirmation(dispatched: dict[str, Any], language: Optional[str], when: str) -> str:
    """Sedi's text for a medication dispatch result: the next interview question, or the created reminder."""
    lang = _lang(language)
    stage = dispatched.get("interview")
    if stage == "ask_repeat":
        return sedi_copy.t("medication.chat.q.ask_repeat", lang, when=when)
    if stage == "ask_same":
        return sedi_copy.t("medication.chat.q.ask_same", lang, names=dispatched.get("names", ""))
    if stage == "ask_reason_promoted":
        return sedi_copy.t("medication.chat.q.ask_reason_promoted", lang, name=dispatched.get("name", ""), times=dispatched.get("times", ""))
    flow = dispatched.get("flow")
    if flow == "dose_added":
        return sedi_copy.t("medication.chat.dose_added", lang, name=dispatched.get("name", ""), time=dispatched.get("time", ""), times=dispatched.get("times", ""))
    if flow == "dose_exists":
        return sedi_copy.t("medication.chat.dose_exists", lang, name=dispatched.get("name", ""), time=dispatched.get("time", ""))
    if flow == "promoted":
        return sedi_copy.t("medication.chat.promoted.done", lang, name=dispatched.get("name", ""), times=dispatched.get("times", ""))
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
    # Codex P2 round 7 (PR 185): the question was stored in the language of ITS turn; the next request may carry another
    # Accept-Language, so the markers of every supported language are tried (the request language first).
    langs = [_lang(language)] + [c for c in ("fa", "en", "ar") if c != _lang(language)]
    for lang in langs:
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


def _original_request(
    turns: list[Any], language: Optional[str], timezone_name: Optional[str], allow_dated: bool = False
) -> Optional[tuple[Any, str]]:
    from backend.app.services.intelligence.reminder_event_readiness import parse_reminder_event_draft
    from backend.app.services.medication_care import pill_registry as reg

    # «tomorrow at 9 …» -> «every day» was answered in an EARLIER turn: that dated request is a DAILY series from then on
    repeat_confirmed: set[str] = set()
    for idx, t in enumerate(turns):
        if idx and _stage_of(getattr(t, "sedi_response", None), language) == "ask_repeat":
            answer = _fold(str(getattr(turns[idx - 1], "user_message", "") or ""))
            if _EVERY.search(answer) and not _ONCE.search(answer):
                repeat_confirmed.add(str(getattr(t, "user_message", "") or ""))
    for text, t in _request_candidates(turns):
        if not is_medication_text(text):
            continue
        draft, missing = parse_reminder_event_draft(
            message=text, timezone_name=timezone_name or "UTC", now_utc=t.created_at, language=language
        )
        if draft is None or missing is not None:
            continue
        if not _is_recurring(draft.recurrence_rule):
            dated = reg.has_day_word(text, timezone_name, t.created_at)
            if dated and text in repeat_confirmed:
                draft, dated = reg.as_daily(draft), False  # the user answered «every day»
            if dated and not allow_dated:
                continue
            if not dated and not _is_recurring(draft.recurrence_rule):
                draft = reg.as_daily(draft)  # no day word: another DAILY dose (R-103 am.2)
        if fire_times(draft) is not None and (allow_dated or not has_future_start(draft, t.created_at)):
            return (draft, text)
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


def _once_event(db: Session, user_id: int, draft: Any, text: str, lang: str, timezone_name: Optional[str]) -> Optional[str]:
    """The plain reminder event (no interview): the user said «just once», or a daily series that starts in the future."""
    from backend.app.services.intelligence.reminder_event_dispatch import confirmation_message, dispatch_reminder_user_event

    res = dispatch_reminder_user_event(
        db, user_id=user_id, message=text, timezone_name=timezone_name, draft=draft, language=lang, skip_medication_interview=True
    )
    return confirmation_message(res, lang)


def _after_promoted(db: Session, user_id: int, lang: str, last: str, message: str, timezone_name: Optional[str] = None) -> Optional[str]:
    """The reason answer after an older reminder was promoted: the companionship becomes ONE tracked commitment (A3); a non-answer
    just closes the step. A long message is another topic (None -> normal flow)."""
    from backend.app.services.medication_care import pill_registry as reg

    quoted = _QUOTED.search(last)
    name = quoted.group(1).strip() if quoted else ""
    text = _fold(message).strip()
    # a long message is another topic, and an INDEPENDENT reminder request keeps its own routing (Codex P2, PR 193)
    if len(text.split()) > 40 or _is_new_reminder_request(message, lang, timezone_name):
        return None
    reply = sedi_copy.t("medication.chat.promoted.done", lang, name=name, times=reg.times_text(reg.times_of(db, user_id, name), lang))
    if not (insists(message) or _NON_ANSWER.match(text) or _CANCEL.search(text)) and _accompany(db, user_id, lang, name, message):
        reply = reply + " " + sedi_copy.t("medication.chat.created.followup_promise", lang)
    return reply


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
        if stage == "ask_reason_promoted":  # the promotion is already done; nothing of the original request is needed
            return _after_promoted(db, user_id, lang, last, message, timezone_name)
        original = _original_request(turns, language, timezone_name, allow_dated=(stage == "ask_repeat"))
        if original is None:
            return None
        draft, orig_text = original[0], original[1]
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

        # an explicit withdrawal («don't set the reminder», «یادآور رو نمی‌خوام») ends it: nothing is created (Codex P2, PR 185)
        if _CANCEL.search(text):
            return sedi_copy.t("medication.chat.cancelled", lang)
        # the two new questions: a non-answer / insistence takes the safe route - nothing the user asked for is lost
        if stage == "ask_repeat" and (insists(message) or _NON_ANSWER.match(text)):
            return _once_event(db, user_id, draft, orig_text, lang, timezone_name)
        if stage == "ask_same" and (insists(message) or _NON_ANSWER.match(text)):
            return finish(None, "medication.chat.created.insist_named", "medication.chat.created.insist_unnamed")
        # a non-answer / insistence ends the interview now: the request is never lost
        if insists(message) or _NON_ANSWER.match(text):
            return finish(name, "medication.chat.created.insist_named", "medication.chat.created.insist_unnamed")
        # an INDEPENDENT reminder request («فردا ساعت ۱۰ جلسه را یادم بنداز») is never taken as an interview answer: it keeps its
        # normal routing, otherwise it would be swallowed and lost (Codex P2, PR 185)
        if _is_new_reminder_request(message, lang, timezone_name):
            return None
        if stage == "ask_repeat":
            once, every = bool(_ONCE.search(text)), bool(_EVERY.search(text))
            if once and not every:
                return _once_event(db, user_id, draft, orig_text, lang, timezone_name)
            if every and not once:
                from backend.app.services.medication_care import pill_registry as reg

                daily = reg.as_daily(draft)
                res = _begin(db, user_id=user_id, message=orig_text, draft=daily, language=lang, timezone_name=timezone_name)
                if res is None:  # a series that starts in the future stays a plain repeating event (known gap, DEBT-076)
                    return _once_event(db, user_id, daily, orig_text, lang, timezone_name)
                return confirmation(res, lang, "")
            from backend.app.services.intelligence.reminder_event_readiness import describe_when

            return sedi_copy.t("medication.chat.q.ask_repeat", lang, when=describe_when(draft, lang, now))
        if stage == "ask_same":
            from backend.app.services.medication_care import pill_registry as reg

            pills = reg.existing_pills(db, user_id)
            if reg.says_new(text):
                return sedi_copy.t("medication.chat.q.ask_name", lang)
            hit = reg.pick(text, pills)
            if hit is None:
                return sedi_copy.t("medication.chat.q.ask_same", lang, names=reg.names_text(pills, lang))
            res = _same_action(db, user_id=user_id, pill=hit, draft=draft, lang=lang)
            return confirmation(res, lang, "") if res is not None else None
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
