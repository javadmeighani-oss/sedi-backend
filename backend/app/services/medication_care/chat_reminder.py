"""R-088 / R-091 (D-382..D-384), package A1: a pill reminder asked for IN CHAT goes to the MEDICATION OWNER.

Before: «هر روز ساعت ۲ یادم بنداز قرص بخورم» created a generic UserEvent, so Sedi never asked which pill, never counted doses
and never reached the dose-confirmation / user_done machinery that already exists for medications.

Now (recurring pill reminders only):
1. ``create_from_draft`` - UserMedication + schedule through ``user_medication_service`` (single owner, R-005). The reminder
   exists at once, so nothing is lost; the name may still be provisional.
2. The confirmation states WHAT/WHEN and asks ONE question: which pill (the exact name on the box, or a photo of the box /
   prescription when unsure). The correct name is critical (R-088 amendment 3), so a name found in the message is also
   confirmed against the box.
3. ``bind_name_answer`` - the next short reply is read as the answer: a new name renames the user's medication, «yes»
   keeps it. The introduction of the medicine (what it is used for) is package A2.

Fail-open: any error returns ``None`` and the caller keeps the old UserEvent path. Kill switch (code default ON, no env
change needed): SEDI_MEDICATION_CHAT_OWNER_DISABLED=1.
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

_ARABIC_MARKS = re.compile("[ً-ٰٟـ‌‏‎]")
_FOLD = (("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("ة", "ه"))

# Medicine words (fa / ar / en). «داروخانه» / pharmacy is a place, not a medicine.
_MED_WORD = re.compile(
    r"(?<![؀-ۿA-Za-z])[بلو]?(?:قرص|کپسول|آمپول|شربت|قطره|دارو|ویتامین|مکمل|حبوب|دوائ|دواء|ادویه|أدویه|كبسولة|كبسول|"
    r"pills?|tablets?|capsules?|medicines?|medications?|vitamins?|supplements?|meds?)"
    r"(?:ها|های|هام|ام|م|ت|ش|ی|ي|ه|ك|نا|مو)?"
    r"(?![؀-ۿA-Za-z])",
    re.I,
)
_PHARMACY = re.compile(r"داروخانه|داروساز|pharmac|صيدلي", re.I)

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
    "the my a an to at every day daily morning evening night noon please remind me take pill pills tablet tablets capsule capsules medicine medicines medication medications vitamin vitamins supplement supplements meds med".split()
)
_YES = re.compile(r"^(?:بله|آره|اره|ایول|درسته|درست|همینه|همین|صحیح|اوهوم|yes|yeah|yep|correct|right|نعم|صحيح|أجل)\b", re.I)
_NO = re.compile(r"^(?:نه|نخیر|خیر|no|nope|لا)\b", re.I)


def _fold(text: str) -> str:
    out = text or ""
    for a, b in _FOLD:
        out = out.replace(a, b)
    return _ARABIC_MARKS.sub("", out)


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def is_medication_text(text: str) -> bool:
    folded = _fold(text)
    return bool(_MED_WORD.search(folded)) and not _PHARMACY.search(folded)


def extract_pill_name(text: str) -> Optional[str]:
    """A medicine name written right after «قرص/کپسول/داروی…» (or «X pill»). None when uncertain - the user is then asked."""
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


def _lang(language: Optional[str]) -> str:
    return language if language in ("fa", "ar", "en") else "en"


def provisional_name(language: Optional[str]) -> str:
    return sedi_copy.t(PROVISIONAL_KEY, _lang(language))


def _hhmm(draft: Any) -> Optional[str]:
    start = getattr(draft, "starts_at_local", None)
    return start.strftime("%H:%M") if isinstance(start, datetime) else None


_BYDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _days_of_week(rule: Optional[str]) -> Optional[str]:
    """«FREQ=WEEKLY;BYDAY=MO,TH» -> «0,3»; daily -> None (every day)."""
    m = re.search(r"BYDAY=([A-Z,]+)", rule or "")
    if not m:
        return None
    days = sorted({_BYDAY[d] for d in m.group(1).split(",") if d in _BYDAY})
    return ",".join(str(d) for d in days) or None


def _is_recurring(rule: Optional[str]) -> bool:
    return bool(rule) and ("FREQ=DAILY" in rule or "FREQ=WEEKLY" in rule)


def create_from_draft(
    db: Session, *, user_id: int, message: str, draft: Any, language: Optional[str], timezone_name: Optional[str]
) -> Optional[dict[str, Any]]:
    """Create the medication + schedule for a recurring pill reminder; None = not applicable / fail-open."""
    try:
        if not enabled() or not is_medication_text(message) or not _is_recurring(getattr(draft, "recurrence_rule", None)):
            return None
        hhmm = _hhmm(draft)
        if not hhmm:
            return None
        from backend.app.schemas.medical import UserMedicationCreateIn
        from backend.app.services import user_medication_service as svc

        lang = _lang(language)
        found = extract_pill_name(message)
        name = found or provisional_name(lang)
        try:
            out = svc.create_user_medication(
                db,
                user_id,
                UserMedicationCreateIn(name=name, reminder_times=[hhmm], timezone=timezone_name or None),
            )
        except svc.DuplicateUserMedicationError:
            return {"kind": "medication", "created": False, "duplicate": True, "name": name, "named": bool(found), "time": hhmm}
        days = _days_of_week(getattr(draft, "recurrence_rule", None))
        if days:
            um = db.query(models.UserMedication).filter(models.UserMedication.id == out["id"]).first()
            if um is not None:
                for row in um.schedules:
                    row.days_of_week = days
                db.commit()
        return {
            "kind": "medication",
            "created": True,
            "duplicate": False,
            "user_medication_id": out.get("id"),
            "name": name,
            "named": bool(found),
            "time": hhmm,
            "days": days,
        }
    except Exception:  # noqa: BLE001 - chat must never break; the caller falls back to the UserEvent path
        logger.exception("[R-088] chat medication create failed; falling back to UserEvent")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def confirmation(dispatched: dict[str, Any], language: Optional[str], when: str) -> str:
    """WHAT + WHEN + ONE question (which pill / exact name or a photo of the box)."""
    lang = _lang(language)
    if dispatched.get("named"):
        return sedi_copy.t("medication.chat.confirm_named", lang, name=dispatched.get("name", ""), when=when)
    return sedi_copy.t("medication.chat.confirm_unnamed", lang, when=when)


# --- the answer to «which pill?» ----------------------------------------------------------------------------------
def _asked_for_pill(last_sedi_reply: Optional[str], language: Optional[str]) -> bool:
    text = _fold(last_sedi_reply or "")
    markers = sedi_copy.variants("medication.chat.markers", _lang(language), "fa")
    return any(_fold(mk) in text for mk in markers)


def _candidate_name(message: str) -> Optional[str]:
    text = _fold(message).strip().strip("«»\"'.؟?!،, ")
    if not text or len(text.split()) > MAX_ANSWER_WORDS or _YES.match(text) or _NO.match(text):
        return None
    cleaned = re.sub(r"^(?:اسمش|اسم\s*آن|نامش|اسم|نام|قرص|داروی|دارو|کپسول|its|it is|it's|called|name is)\s+", "", text, flags=re.I)
    cleaned = re.sub(r"\s+(?:است|هست|ه|می‌باشد)$", "", cleaned).strip()
    return cleaned[:120] or None


def _latest_pending(db: Session, user_id: int, now: datetime) -> Optional[tuple[models.UserMedication, models.Medication]]:
    since = now.replace(tzinfo=None) - BIND_WINDOW
    row = (
        db.query(models.UserMedication)
        .filter(models.UserMedication.user_id == user_id, models.UserMedication.created_at >= since)
        .order_by(models.UserMedication.created_at.desc())
        .first()
    )
    if row is None:
        return None
    med = db.query(models.Medication).filter(models.Medication.id == row.medication_id).first()
    return (row, med) if med is not None else None


def last_sedi_reply(db: Session, user_id: int) -> Optional[str]:
    """Sedi's previous reply (consent-gated raw turn, R-021). None without consent / history: the binding then simply does not apply."""
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission
        from backend.app.services.i7.retention import query_eligible_raw

        if not has_permission(db, user_id, PERM_READ):
            return None
        for row in query_eligible_raw(db, user_id, limit=3):
            reply = str(getattr(row, "sedi_response", "") or "").strip()
            if reply:
                return reply
    except Exception:  # noqa: BLE001
        return None
    return None


def bind_name_answer(
    db: Session, *, user_id: int, message: str, last_sedi_reply: Optional[str], language: Optional[str],
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Read a short reply to «which pill?» as the answer. Returns Sedi's reply text or None when it does not apply."""
    try:
        if not enabled() or not _asked_for_pill(last_sedi_reply, language):
            return None
        moment = now or datetime.now(timezone.utc)
        pending = _latest_pending(db, user_id, moment)
        if pending is None:
            return None
        um, med = pending
        lang = _lang(language)
        text = _fold(message).strip()
        hhmm = None
        sched = list(um.schedules)
        if sched:
            hhmm = sched[0].time_of_day.strftime("%H:%M")
        if _YES.match(text):
            if med.name == provisional_name(lang):  # «yes» to «which pill?» carries no name: ask once more
                return sedi_copy.t("medication.chat.ask_again", lang)
            return sedi_copy.t("medication.chat.kept", lang, name=med.name, time=hhmm or "")
        name = _candidate_name(message)
        if name is None:
            return None
        from backend.app.services import user_medication_service as svc

        new_med = svc.find_or_create_medication(db, name)
        if new_med.id != med.id:
            clash = (
                db.query(models.UserMedication)
                .filter(models.UserMedication.user_id == user_id, models.UserMedication.medication_id == new_med.id)
                .first()
            )
            if clash is not None:  # already tracked under that name: keep one owner row, tell the user
                return sedi_copy.t("medication.chat.already_tracked", lang, name=new_med.name)
            um.medication_id = new_med.id
            db.commit()
        return sedi_copy.t("medication.chat.bound", lang, name=new_med.name, time=hhmm or "")
    except Exception:  # noqa: BLE001
        logger.exception("[R-088] medication name binding failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
