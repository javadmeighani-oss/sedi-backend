"""R-103 step A: «change the time of my reminder» from chat REALLY changes it (and Sedi never says «changed» when it did not).

Pilot 2026-11-19: the user asked to move the daily pill reminder from 14:00 to 16:00; the model answered «I changed it» but no
code path existed, the event kept 14:00. This module is that path. It owns NO storage: the change goes through the two existing
owners (UserEvent -> ``gate2_data_service.update_event``; UserMedication schedule -> ``user_medication_service.update_user_medication``
- the very services the «My schedule» page uses), so I10 simply reads the new time on its next tick (R-005).

Honest by construction: the confirmation is built from what the owner returned (WHAT and the old/new time, R-026/R-103); when the
reminder cannot be identified or the hour is ambiguous Sedi asks ONE question; a failed write says so and changes nothing.
Deterministic, fail-open (None -> the normal flow), no DB schema, no flag.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models, sedi_copy
from backend.app.services.intelligence import reminder_event_readiness as _rer

logger = logging.getLogger(__name__)

_CHANGE = re.compile(
    # explicit change verb (fa / ar / en); a bare «set a reminder at 5» is a NEW reminder and never matches here
    r"(?:تغییر|عوض|جابه?\s*جا|منتقل|تعویض)\s*(?:بده|بدم|کن|کنی|کنید|بدین|شود|بشه|بشود|می\s*کنم|میکنم|بزن)|"
    r"(?:زمان|ساعت|وقت)(?:ش|شو|شون|اش|ـش)?\s*(?:رو|را)?\s*(?:بکن|بذار|بزار|بگذار|ببر)|"
    r"\b(?:change|move|shift|reschedule|postpone)\b.{0,40}\b(?:to|at|for)\b|"
    r"\b(?:change|move|shift)\s+(?:it|its\s+time|the\s+time|the\s+reminder)\b|"
    r"(?:غ[يی]ّ?ر|بدّل|بدل|انقل|عدّل|عدل)\w*\s+(?:ال)?(?:موعد|وقت|ساعة|تذك[يی]ر)",
    re.I,
)
# Codex P1 (PR 192): «don't change my reminder to 4 pm» / «تغییرش نده» is the opposite of a request.
_NEGATED = re.compile(
    r"(?:نه\s+|لازم\s+نیست\s+|نمی\s*?خوام\s+|نمیخوام\s+)?(?:تغییر|عوض|جابه?\s*جا|منتقل)\w*\s+(?:نده|نکن|نکنید|ندین|نشه|نشود)|"
    r"(?:نمی\s*?خوام|نمیخوام|نمی\s*?خواهم|لازم\s+نیست)\b.{0,40}(?:تغییر|عوض|جابه?\s*جا)|"
    r"\b(?:don'?t|do\s+not|never|no\s+need\s+to|please\s+don'?t|stop|without)\b.{0,25}\b(?:change|move|shift|reschedule|postpone)\b|"
    r"\bno\s+need\s+to\s+(?:change|move)\b|"
    r"لا\s+(?:تغ[يی]ّ?ر|تبدّ?ل|تنقل|تعدّ?ل)|ما\s+(?:بدي|أريد|اريد)\s+(?:أغ[يی]ّ?ر|تغ[يی]ير)",
    re.I,
)
_STOP = frozenset(
    "خوردن یادآوری یادآور هر روز ساعت را رو به برای و من تو با از در این آن همین بعد قبل صبح عصر شب ظهر "
    "the a an to of my me at every day take remind reminder time for and "
    "تذكير الساعة كل يوم".split()
)
_PRONOUN = re.compile(r"(?:زمان|ساعت|وقت)(?:ش|شو|شون|اش)\b|\b(?:it|its\s+time|that\s+one)\b|(?:موعده|وقته)")
_TOKEN = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_MARK = {
    "period": {"fa": "برای تغییر زمان", "ar": "لتغيير الموعد", "en": "For the time change"},
    "which": {"fa": "کدام یادآوری را می‌گویی", "ar": "أي تذكير تقصد", "en": "Which reminder do you mean"},
}


def _lang(language: Optional[str]) -> str:
    return language if language in ("fa", "ar", "en") else "en"


def _norm(text: str) -> str:
    return _rer._normalize(text or "")


def is_change_request(message: str) -> bool:
    """An explicit request to change the time of something that already exists (needs a change verb)."""
    text = _norm(message)
    return bool(text and _CHANGE.search(text) and not _NEGATED.search(text))


def _times_in(text: str) -> list[tuple[int, int, int, str, int]]:
    """Every clock time named in the text, in order: (hour24, minute, day_shift, own_words). «from 4 pm to 9 am» -> two items,
    each resolved with ITS OWN period words (the text between the previous time and the next one), never the whole sentence
    (Codex P1, PR 192)."""
    spans: list[tuple[int, int, Any, Any]] = []
    for rx in (_rer._TIME_AFTER_WORD, _rer._TIME_H_AND_MIN, _rer._TIME_COLON, _rer._TIME_SUFFIX):
        for m in rx.finditer(text):
            spans.append((m.start(), m.end(), m, rx))
    kept: list[tuple[int, int, Any]] = []
    for start, end, m, _rx in sorted(spans, key=lambda x: (x[0], -(x[1] - x[0]))):
        if any(start < b and a < end for a, b, _m in kept):  # the same spoken time matched by two patterns counts once
            continue
        kept.append((start, end, m))
    out: list[tuple[int, int, int, str, int]] = []
    for i, (start, end, m) in enumerate(kept):
        lo = start if i else 0  # a period word AFTER a time («۴ عصر») belongs to that time, not to the next one
        hi = kept[i + 1][0] if i + 1 < len(kept) else len(text)
        window = text[lo:hi]
        d = m.groupdict()
        minute = int(d.get("min") or d.get("min2") or (30 if d.get("half") else 0) or 0)
        resolved = _rer._apply_period(int(m.group("h")), minute, window, d.get("ap") or "")
        if resolved is not None:
            out.append((resolved[0], resolved[1], resolved[2], window, start))
    return out


_FROM = re.compile(r"(?:\bfrom\b|(?:^|\s)از\s|(?:^|\s)من\s)", re.I)
_INSTEAD = re.compile(r"(?:\binstead\s+of\b|\brather\s+than\b|به\s*جای|بجای|بدل|بدلا\s+من|بدلاً\s+من)", re.I)


def _roles(text: str, times: list[tuple[int, int, int, str, int]]) -> tuple[tuple, Optional[tuple]]:
    """(destination, old-or-identifying time). «from 2 to 4» -> old first; «to 4 pm instead of 2 pm» and a clarification answer that
    names a reminder by its time («Dentist at 9 am») -> the FIRST time is the destination (Codex P2, PR 192)."""
    if len(times) == 1:
        return times[0], None
    first, last = times[0], times[-1]
    if _FROM.search(text[: first[4]]) and not _INSTEAD.search(text):
        return last, first
    return first, times[1]


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _TOKEN.findall(_norm(text).lower()):
        tok = raw
        for suffix in ("مو", "شو", "تو", "م", "ت", "ش"):
            if len(tok) >= 4 and tok.endswith(suffix) and len(tok) - len(suffix) >= 3:
                tok = tok[: -len(suffix)]
                break
        if tok not in _STOP:
            out.add(tok)
    return out


def _candidates(db: Session, user_id: int, now_utc: datetime) -> list[dict[str, Any]]:
    """Active reminders the user can mean: repeating events + future one-time events + medication schedules."""
    out: list[dict[str, Any]] = []
    now_naive = now_utc.replace(tzinfo=None)
    for e in (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.user_id == user_id,
            models.UserEvent.reminder_enabled == True,  # noqa: E712
            models.UserEvent.status.in_(["scheduled", "confirmed"]),
        )
        .order_by(models.UserEvent.id.desc())
        .limit(30)
        .all()
    ):
        if e.starts_at is None or (e.valid_to and e.valid_to <= now_naive):
            continue
        recurring = bool((e.recurrence_rule or "").strip())
        if not recurring and e.starts_at < now_naive - timedelta(days=1):
            continue
        out.append({"kind": "event", "obj": e, "title": e.title, "hhmm": _hhmm(e.starts_at.hour, e.starts_at.minute), "recurring": recurring})
    for um in (
        db.query(models.UserMedication)
        .filter(models.UserMedication.user_id == user_id, models.UserMedication.reminder_enabled == True)  # noqa: E712
        .limit(20)
        .all()
    ):
        med = db.query(models.Medication).filter(models.Medication.id == um.medication_id).first()
        for row in um.schedules or []:
            if row.time_of_day is None:
                continue
            out.append({"kind": "med", "obj": um, "row": row, "title": getattr(med, "name", "") or "", "hhmm": _hhmm(row.time_of_day.hour, row.time_of_day.minute), "recurring": True})
    return out


def _pick(
    cands: list[dict[str, Any]], context: str, old_hhmm: Optional[str], message: str = ""
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """(chosen, shortlist). chosen is None when the reminder cannot be identified with confidence. A reminder NAMED in the message
    is checked first: a wrong old time must not move a different reminder (Codex P1, PR 192)."""
    named = [c for c in cands if _tokens(c["title"]) & _tokens(message)] if message else []
    base = named or cands
    pool = [c for c in base if not old_hhmm or c["hhmm"] == old_hhmm] or base
    if len(pool) == 1:
        return pool[0], pool
    ctx = _tokens(context)
    scored = sorted(((len(_tokens(c["title"]) & ctx), i, c) for i, c in enumerate(pool)), key=lambda x: (-x[0], x[1]))
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][2], pool
    return None, pool


def _day_word(lang: str, key: str) -> str:
    return sedi_copy.t(f"reminder.reschedule.day_{key}", lang)


class _PastTime(Exception):
    """The requested date + time is already behind: nothing is changed."""


class _Collision(Exception):
    """The new time is already another dose of the same medicine: nothing is changed."""


def _lead_minutes(e: Any) -> int:
    """The advance time the event keeps (its reminder fires this long BEFORE starts_at); 0 = at the time (pills, chat reminders)."""
    import json

    try:
        raw = json.loads(getattr(e, "reminder_offsets_json", None) or "[]")
        return max([int(x) for x in raw if isinstance(x, (int, float)) and x > 0] or [0])
    except Exception:  # noqa: BLE001
        return 0


def _apply_event(
    db: Session, user_id: int, cand: dict[str, Any], new: tuple[int, int, int], now_utc: datetime, text: str = ""
) -> tuple[str, str, int]:
    from backend.app.schemas.gate2 import EventUpdateIn
    from backend.app.services.gate2_data_service import update_event

    e = cand["obj"]
    start = e.starts_at.replace(hour=new[0], minute=new[1], second=0, microsecond=0)
    day_key = ""
    if not cand["recurring"]:
        import pytz

        try:
            tz = pytz.timezone(e.timezone or "Asia/Tehran")
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone("Asia/Tehran")
        now_local = now_utc.astimezone(tz).replace(tzinfo=None)
        said = _rer._resolve_date(text, now_local) if text else None
        if said is not None:  # an explicit day (tomorrow, a weekday, a date) wins over the event's old date (Codex P2, PR 192)
            start = datetime.combine(said.date(), time(new[0], new[1])) + timedelta(days=new[2])
            if start <= now_local:
                raise _PastTime()
        else:
            start = start + timedelta(days=new[2])
            while start <= now_local:  # no day = the next time that clock shows (R-042), also for a reminder that expired days ago
                start = start + timedelta(days=1)
        day_key = "today" if start.date() == now_local.date() else "tomorrow" if start.date() == (now_local + timedelta(days=1)).date() else ""
    ends = getattr(e, "ends_at", None)
    # the duration is kept: a populated end time moves by the same delta as the start (Codex P2, PR 192)
    update_event(db, user_id, int(e.id), EventUpdateIn(starts_at=start, ends_at=(ends + (start - e.starts_at)) if ends else None))
    return _hhmm(start.hour, start.minute), day_key, _lead_minutes(e)


def _apply_med(db: Session, user_id: int, cand: dict[str, Any], new: tuple[int, int, int]) -> str:
    from backend.app.services import user_medication_service as svc

    um, row = cand["obj"], cand["row"]
    old_key = svc.format_time_of_day(row.time_of_day)
    new_key = _hhmm(new[0], new[1])
    if any(svc.format_time_of_day(r.time_of_day) == new_key for r in (um.schedules or []) if r is not row and r.time_of_day is not None):
        raise _Collision()  # the owner would merge the two doses and silently drop one weekday filter (Codex P2, PR 192)
    try:
        svc.move_schedule_time(db, user_id, int(um.id), old_key, new_key)  # one transaction, weekday filter kept
    except svc.ScheduleTimeCollisionError:
        raise _Collision()
    return new_key


def handle(
    db: Session, *, user_id: int, message: str, language: Optional[str], now_utc: Optional[datetime] = None, context: str = ""
) -> Optional[str]:
    """Sedi's reply when [message] asks to change the time of an existing reminder; None = not applicable (normal flow)."""
    try:
        lang = _lang(language)
        text = _norm(message)
        if not text or not _CHANGE.search(text) or _NEGATED.search(text):
            return None
        now = now_utc or datetime.now(timezone.utc)
        times = _times_in(text)
        if not times:
            return None  # a change without a new time is left to the normal conversation (it asks)
        dest, old_t = _roles(text, times)
        hour12 = _rer.ambiguous_period_hour(dest[3])  # the NEW time's own words decide whether it is ambiguous
        if hour12 is not None:
            return sedi_copy.t("reminder.reschedule.ask_period", lang, hour=hour12)
        new = dest[:3]
        old_hhmm = _hhmm(old_t[0], old_t[1]) if old_t is not None else None
        cands = _candidates(db, user_id, now)
        if not cands:
            return None  # nothing to change: the normal flow answers (and the guard strips any «I changed it» claim)
        ctx_tokens = _tokens(text + " " + (context or ""))
        # «change my dinner to 8 pm» is not about a reminder: act only when the message points at one (reminder word, «its time»,
        # or a word of a reminder's own title in the message / the last reply)
        if not (_rer._REMINDER_WORDS.search(text) or _PRONOUN.search(text) or any(_tokens(c["title"]) & ctx_tokens for c in cands)):
            return None
        chosen, pool = _pick(cands, text + " " + (context or ""), old_hhmm, text)
        if chosen is None:
            lines = "؛ ".join(f"«{c['title']}» {c['hhmm']}" for c in pool[:3]) if lang != "en" else "; ".join(f"“{c['title']}” {c['hhmm']}" for c in pool[:3])
            return sedi_copy.t("reminder.reschedule.ask_which", lang, list=lines)
        old = chosen["hhmm"]
        lead = 0
        try:
            if chosen["kind"] == "event":
                new_hhmm, day_key, lead = _apply_event(db, user_id, chosen, new, now, text)
            else:
                new_hhmm, day_key = _apply_med(db, user_id, chosen, new), ""
        except _PastTime:
            return sedi_copy.t("reminder.reschedule.past", lang)
        except _Collision:
            return sedi_copy.t("reminder.reschedule.collision", lang, title=chosen["title"], new=_hhmm(new[0], new[1]))
        except Exception:  # noqa: BLE001 - nothing is claimed that did not happen
            logger.exception("[R-103] reminder reschedule failed")
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return sedi_copy.t("reminder.reschedule.failed", lang)
        day = _day_word(lang, day_key) if day_key else ""
        if lead > 0:  # the event itself moved; its advance reminder keeps its lead time (said honestly, Codex P2, PR 192)
            return sedi_copy.t("reminder.reschedule.done_lead", lang, title=chosen["title"], old=old, new=new_hhmm, day=day, lead=lead)
        return sedi_copy.t("reminder.reschedule.done", lang, title=chosen["title"], old=old, new=new_hhmm, day=day)
    except Exception:  # noqa: BLE001
        logger.exception("[R-103] reminder reschedule skipped")
        return None


def context_of(turns: list[Any], answered_question: bool) -> str:
    """The Sedi replies that give a reminder its context. When the user is ANSWERING one of this flow's questions, the newest
    reply is that question (with every option listed): it is left out, otherwise all options score alike (Codex P2, PR 192)."""
    use = turns[1:3] if answered_question else turns[:2]
    return " ".join(str(getattr(t, "sedi_response", "") or "") for t in use)


def pending_request(turns: list[Any], answer: str, language: Optional[str]) -> Optional[str]:
    """Like ``pending_prior_request`` but follows a CHAIN of this flow's questions (at 5 -> morning or evening? -> pm -> which
    reminder? -> Dentist): the original request and every answer, oldest first, plus this answer (Codex P2, PR 192)."""
    parts: list[str] = []
    for t in turns:
        reply = _norm(str(getattr(t, "sedi_response", "") or "")).lower()
        if not reply or not any(_norm(m).lower() in reply for kind in _MARK.values() for m in kind.values()):
            break
        parts.append(str(getattr(t, "user_message", "") or "").strip())
    if not parts or not parts[0]:
        return None
    newest_reply = _norm(str(getattr(turns[0], "sedi_response", "") or "")).lower()
    if any(_norm(m).lower() in newest_reply for m in _MARK["period"].values()) and not _rer._ANY_PERIOD_WORD.search(answer or ""):
        return None
    return " ".join(reversed(parts)) + " " + answer.strip()


def pending_prior_request(last_reply: Optional[str], last_user_message: Optional[str], answer: str, language: Optional[str]) -> Optional[str]:
    """The user's answer to Sedi's own «morning or evening?» / «which reminder?» question of THIS flow, joined to the original
    request so ``handle`` can finish it. None when the last Sedi reply was not one of those two questions."""
    reply = _norm(last_reply or "").lower()
    if not reply or not (last_user_message or "").strip():
        return None
    for kind in ("period", "which"):
        if any(_norm(m).lower() in reply for m in _MARK[kind].values()):
            if kind == "period" and not _rer._ANY_PERIOD_WORD.search(answer or ""):
                return None
            return f"{last_user_message.strip()} {answer.strip()}"
    return None
