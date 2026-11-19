"""R-103 step B: ONE view over the user's existing pills, whichever owner holds them.

A pill lives either in the medicine owner (UserMedication + schedules; the target state) or, for reminders made by the older chat
path, as a repeating UserEvent whose title names a pill. The interview needs both: «is this the same pill or a new one?», adding a
dose to a registered pill, and PROMOTING an older reminder into the medicine owner (user_medication_service.promote_event_to_medication:
one transaction, the older event is soft-cancelled, never deleted). This module owns no storage and no schedule logic.
"""
from __future__ import annotations

import dataclasses
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

_DROP = frozenset("هم خوردن بخورم بخور بخوری مصرف کردن کنم take taking my the to also و a an".split())
# generic CONTAINER words (a name made only of these is generic); «مکمل / ویتامین / vitamin» are names, kept apart
_KIND = frozenset("قرص کپسول آمپول شربت قطره دارو pill pills tablet tablets capsule capsules medicine medication".split())
_CLITIC_BASE = _KIND | frozenset("مکمل ویتامین supplement vitamin".split())
_CLITICS = ("هام", "های", "ها", "مو", "ام", "م", "ت", "ش")
_NEW = re.compile(r"(?:جدید|جديد|دیگه|دیگر|یکی\s+دیگه|متفاوت|\bnew\b|\banother\b|\bdifferent\b|\bother\b|\bnot\s+the\s+same\b|آخر|جديدة)", re.I)
_SAME = re.compile(r"^(?:همان|همون|همین|هم\s*ان|بله|آره|اره|درسته|همینه|اون|آن|نفس|\bsame\b|\byes\b|\bthat\s+one\b|نعم|نفسه|هو\s+نفسه)", re.I)
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _fold(text: str) -> str:
    from backend.app.services.medication_care.chat_reminder import _fold as f

    return f(text or "").replace(chr(0x200C), " ")


def _strip_clitic(tok: str) -> str:
    for c in _CLITICS:
        if tok.endswith(c) and tok[: -len(c)] in _CLITIC_BASE:
            return tok[: -len(c)]
    return tok


def pill_title_name(title: str) -> Optional[str]:
    """«خوردن قرص مکملم» -> «قرص مکمل»; «هم قرصمو بخورم» -> «قرص». None when nothing is left."""
    words = [w for w in _TOKEN.findall(_fold(title).lower())]
    out = [_strip_clitic(w) for w in words if w not in _DROP]
    out = [w for w in out if w not in _DROP]
    return " ".join(out).strip() or None


_UNITS = frozenset("mg mcg g ml iu میلی گرم میکروگرم واحد میلیگرم".split())


def _name_tokens(name: str) -> set[str]:
    return {_strip_clitic(w) for w in _TOKEN.findall(_fold(name).lower())} - _DROP


def _split(name: str) -> tuple[set[str], set[str]]:
    """(identity tokens, strength tokens): «Metformin 500 mg» -> ({metformin}, {500, mg}); container words are not identity."""
    toks = _name_tokens(name)
    dose = {t for t in toks if t.isdigit() or t in _UNITS}
    return toks - dose - _KIND, dose


def same_pill(a: str, b: str) -> bool:
    """The same medicine: identity tokens EQUAL («Vitamin C» is not «Vitamin D») and, when both state a strength, equal strengths
    («Metformin 500 mg» is not «Metformin 1000 mg»). Codex P1, PR 193."""
    ia, da = _split(a)
    ib, db_ = _split(b)
    if ia or ib:
        return ia == ib and (not da or not db_ or da == db_)
    return bool(_name_tokens(a)) and _name_tokens(a) == _name_tokens(b)


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _lead(e: Any) -> int:
    from backend.app.services.intelligence.reminder_reschedule import _lead_minutes

    return _lead_minutes(e)


def existing_pills(db: Session, user_id: int) -> list[dict[str, Any]]:
    """[{kind: 'med'|'event', id, name, times:[HH:MM], rule}] - registered pills first, then older repeating pill reminders."""
    from backend.app.services.medication_care.chat_reminder import is_medication_text

    pills: list[dict[str, Any]] = []
    for um in (
        db.query(models.UserMedication)
        .filter(models.UserMedication.user_id == user_id, models.UserMedication.reminder_enabled == True)  # noqa: E712
        .order_by(models.UserMedication.id.asc())
        .limit(10)
        .all()
    ):
        med = db.query(models.Medication).filter(models.Medication.id == um.medication_id).first()
        name = getattr(med, "name", "") or ""
        times = sorted(_hhmm(r.time_of_day.hour, r.time_of_day.minute) for r in (um.schedules or []) if r.time_of_day is not None)
        if name:
            pills.append({"kind": "med", "id": int(um.id), "name": name, "times": times, "rule": None})
    now = datetime.utcnow()
    for e in (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.user_id == user_id,
            models.UserEvent.reminder_enabled == True,  # noqa: E712
            models.UserEvent.status.in_(["scheduled", "confirmed"]),
            models.UserEvent.recurrence_rule.isnot(None),
        )
        .order_by(models.UserEvent.id.asc())
        .limit(20)
        .all()
    ):
        if e.starts_at is None or (e.valid_to and e.valid_to <= now) or not is_medication_text(e.title or ""):
            continue
        if _lead(e) > 0:  # an advance reminder (fires BEFORE the dose time) cannot become a dose schedule: it stays an event
            continue
        name = pill_title_name(e.title or "")
        if not name or any(same_pill(name, p["name"]) for p in pills):
            continue
        pills.append({"kind": "event", "id": int(e.id), "name": name, "times": [_hhmm(e.starts_at.hour, e.starts_at.minute)], "rule": e.recurrence_rule})
    return pills


def match(found_name: Optional[str], pills: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not found_name:
        return None
    return next((p for p in pills if same_pill(found_name, p["name"])), None)


def says_new(answer: str) -> bool:
    return bool(_NEW.search(_fold(answer)))


def pick(answer: str, pills: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The pill an answer points at: a word of its name, or - with exactly one pill - a plain «same / همان»."""
    text = _fold(answer).strip()
    toks = _name_tokens(text) - _KIND
    exact = [p for p in pills if _split(p["name"])[0] and _split(p["name"])[0] <= toks] if toks else []
    if len(exact) == 1:  # the answer contains ALL identity words of exactly one pill («vitamin d» -> Vitamin D, not Vitamin C)
        return exact[0]
    named = [p for p in pills if (_name_tokens(p["name"]) - _KIND) & toks] if toks else []
    if len(named) == 1:
        return named[0]
    if len(pills) == 1 and (named or _SAME.search(text)):
        return pills[0]
    return None


def names_text(pills: list[dict[str, Any]], lang: str) -> str:
    sep = "، " if lang in ("fa", "ar") else ", "
    return sep.join(("«%s»" % p["name"]) if lang != "en" else ("“%s”" % p["name"]) for p in pills[:3])


def times_text(times: list[str], lang: str) -> str:
    return ("، " if lang in ("fa", "ar") else ", ").join(times)


def as_daily(draft: Any) -> Any:
    """The same request as a DAILY series («ساعت ۹ صبح هم …» means every day, Javad 2026-11-19)."""
    return dataclasses.replace(draft, recurrence_rule="FREQ=DAILY")


def has_day_word(message: str, timezone_name: Optional[str], now_utc: Optional[datetime]) -> bool:
    """True when the message names a day (tomorrow, a weekday, a date): Sedi then asks «once or repeating?» (R-103 am.2)."""
    try:
        import pytz

        from backend.app.services.intelligence import reminder_event_readiness as rer

        try:
            tz = pytz.timezone(timezone_name or "Asia/Tehran")
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone("Asia/Tehran")
        moment = now_utc or datetime.now(timezone.utc)
        local_now = (moment if moment.tzinfo else moment.replace(tzinfo=pytz.UTC)).astimezone(tz).replace(tzinfo=None)
        return rer._resolve_date(rer._normalize(message), local_now) is not None
    except Exception:  # noqa: BLE001
        return False


def add_dose(db: Session, user_id: int, pill: dict[str, Any], hhmm: str, days: Optional[str]) -> list[str]:
    """Another daily dose for a REGISTERED pill (medicine owner). Returns the doses; raises ScheduleTimeCollisionError."""
    from backend.app.services import user_medication_service as svc

    out = svc.add_schedule_time(db, user_id, int(pill["id"]), hhmm, days)
    return sorted(out.get("reminder_times") or [hhmm])


def promote(db: Session, user_id: int, pill: dict[str, Any], hhmm: str, days: Optional[str]) -> list[str]:
    """An older repeating reminder becomes a registered pill with its old dose AND the new one; the older event is soft-cancelled."""
    from backend.app.services import user_medication_service as svc

    out = svc.promote_event_to_medication(db, user_id, int(pill["id"]), pill["name"], hhmm, days)
    return sorted(out.get("reminder_times") or [hhmm])


def times_of(db: Session, user_id: int, name: str) -> list[str]:
    for p in existing_pills(db, user_id):
        if p["kind"] == "med" and same_pill(name, p["name"]):
            return p["times"]
    return []
