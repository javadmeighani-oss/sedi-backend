# backend.app.services.i7.memory_explorer
"""H1: the user's memory explorer — calendar, one-day view, search and day notes (I7 owns this read model).

Reuses the existing owners, no new table and no migration (R-005):
- raw chat turns (``memory``) are shown and editable only inside the 30-day retention window (``retention``);
- older days are shown from the derived DAILY summary (``UserPeriodSummary``), life events (``user_events``) and
  I6 facts — never from raw chat text;
- the user's own correction of an OLD derived summary is a *day note* of kind ``correction`` (a ``user_events`` row with
  a bounded JSON marker, like life events); the derived summary itself is never rewritten.
Everything is consent-gated (memory.read / write / forget), ownership-scoped and fails open to empty results.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i7.retention import RAW_VISIBLE_DAYS, query_eligible_raw

NOTE_MARK = "@@SEDI_NOTE@@"
NOTE_EVENT_TYPE = "memory_note"
NOTE_KINDS = ("note", "correction")
MAX_NOTE = 240
MAX_TURN_TEXT = 4000
MAX_CALENDAR_SPAN_DAYS = 70
MAX_SEARCH_RESULTS = 50
_SCAN_CAP = 600

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_STRIP = re.compile("[‌‍ـً-ٰٟ]")


def _has(db: Session, user_id: int, perm: str) -> bool:
    from backend.app.services.i6.consent_service import has_permission

    try:
        return bool(has_permission(db, user_id, perm))
    except Exception:
        return False


def _zone(db: Session, user_id: int):
    import pytz

    from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone

    try:
        name = resolve_validated_user_timezone(db, user_id)
        return pytz.timezone(name), name
    except Exception:
        return pytz.UTC, "UTC"


def _lang(db: Session, user_id: int) -> str:
    try:
        row = db.query(models.User.preferred_language).filter(models.User.id == user_id).first()
        raw = ((row[0] if row else None) or "fa").strip().lower().split("-")[0]
        return raw if raw in ("fa", "en", "ar") else "en"
    except Exception:
        return "fa"


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _local_day(dt: Optional[datetime], zone) -> Optional[date]:
    u = _utc(dt)
    return u.astimezone(zone).date() if u is not None else None


def day_bounds_utc(day: date, zone) -> tuple[datetime, datetime]:
    """[start, end) of a user-local calendar day as aware UTC datetimes."""
    start = zone.localize(datetime.combine(day, time.min))
    end = zone.localize(datetime.combine(day + timedelta(days=1), time.min))
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def norm(text: Any) -> str:
    """Search normalisation: case, Arabic/Persian letter variants, digits, ZWNJ and diacritics."""
    s = str(text or "").translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    return " ".join(_STRIP.sub("", s).lower().split())


def raw_visible_for_day(day: date, zone, *, now: Optional[datetime] = None) -> bool:
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date()
    return 0 <= (today - day).days <= RAW_VISIBLE_DAYS


# ----------------------------------------------------------------------------------------------------------------------
# day notes (user notes and corrections of derived summaries)
# ----------------------------------------------------------------------------------------------------------------------
def _pack_note(kind: str, day: date) -> str:
    return NOTE_MARK + json.dumps({"kind": kind, "day": day.isoformat()}, separators=(",", ":"))


def _parse_note(description: Optional[str]) -> Optional[dict]:
    if not description or not description.startswith(NOTE_MARK):
        return None
    try:
        data = json.loads(description[len(NOTE_MARK):])
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _note_dict(row: models.UserEvent) -> dict[str, Any]:
    meta = _parse_note(row.description) or {}
    return {
        "id": int(row.id),
        "kind": meta.get("kind", "note"),
        "day": meta.get("day"),
        "text": row.title,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _owned_note(db: Session, user_id: int, note_id: int) -> Optional[models.UserEvent]:
    row = (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.id == note_id,
            models.UserEvent.user_id == user_id,
            models.UserEvent.event_type == NOTE_EVENT_TYPE,
            models.UserEvent.status == "completed",
        )
        .first()
    )
    return row if row is not None and _parse_note(row.description) is not None else None


def add_day_note(db: Session, user_id: int, *, day: date, text: str, kind: str = "note") -> Optional[dict[str, Any]]:
    """None when memory.write is not granted or the text is empty."""
    from backend.app.services.i6.consent_service import PERM_WRITE

    clean = " ".join((text or "").split())[:MAX_NOTE]
    if not clean or not _has(db, user_id, PERM_WRITE):
        return None
    kind = kind if kind in NOTE_KINDS else "note"
    zone, _ = _zone(db, user_id)
    noon_utc = zone.localize(datetime.combine(day, time(12, 0))).astimezone(timezone.utc)
    now = _naive_utc(datetime.now(timezone.utc))
    row = models.UserEvent(
        user_id=user_id,
        title=clean,
        description=_pack_note(kind, day),
        event_domain="personal",
        event_type=NOTE_EVENT_TYPE,
        starts_at=_naive_utc(noon_utc),
        status="completed",
        importance="normal",
        reminder_enabled=False,
        source="manual",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _note_dict(row)


def update_day_note(db: Session, user_id: int, note_id: int, *, text: str) -> Optional[dict[str, Any]]:
    from backend.app.services.i6.consent_service import PERM_WRITE

    clean = " ".join((text or "").split())[:MAX_NOTE]
    if not clean or not _has(db, user_id, PERM_WRITE):
        return None
    row = _owned_note(db, user_id, note_id)
    if row is None:
        return None
    row.title = clean
    row.updated_at = _naive_utc(datetime.now(timezone.utc))
    db.commit()
    db.refresh(row)
    return _note_dict(row)


def delete_day_note(db: Session, user_id: int, note_id: int) -> bool:
    """Soft delete (status=cancelled), like life events. Needs memory.forget."""
    from backend.app.services.i6.consent_service import PERM_FORGET

    if not _has(db, user_id, PERM_FORGET):
        return False
    row = _owned_note(db, user_id, note_id)
    if row is None:
        return False
    now = _naive_utc(datetime.now(timezone.utc))
    row.status = "cancelled"
    row.valid_to = now
    row.updated_at = now
    db.commit()
    return True


# ----------------------------------------------------------------------------------------------------------------------
# raw turns (inside the 30-day window only)
# ----------------------------------------------------------------------------------------------------------------------
def _turn_dict(m: models.Memory, zone) -> dict[str, Any]:
    local = _utc(m.created_at).astimezone(zone)
    return {
        "id": int(m.id),
        "time": local.strftime("%H:%M"),
        "created_at": _utc(m.created_at).isoformat(),
        "user_message": m.user_message or "",
        "sedi_response": m.sedi_response,
    }


def _eligible_turns_of_day(db: Session, user_id: int, day: date, zone) -> list[models.Memory]:
    start, end = day_bounds_utc(day, zone)
    rows = query_eligible_raw(db, user_id, limit=_SCAN_CAP * 2)
    return sorted(
        [m for m in rows if m.created_at is not None and start <= _utc(m.created_at) < end],
        key=lambda m: _utc(m.created_at),
    )


def edit_turn(db: Session, user_id: int, memory_id: int, *, user_message: Optional[str], sedi_response: Optional[str]) -> Optional[dict[str, Any]]:
    """The user's own correction of a chat turn still inside the retention window. None when not found / not permitted."""
    from backend.app.services.i6.consent_service import PERM_WRITE
    from backend.app.services.i7.retention import is_raw_visible

    if not _has(db, user_id, PERM_WRITE):
        return None
    row = db.query(models.Memory).filter(models.Memory.id == memory_id, models.Memory.user_id == user_id).first()
    if row is None or not is_raw_visible(row):
        return None
    if user_message is not None:
        text = user_message.strip()[:MAX_TURN_TEXT]
        if not text:
            return None
        row.user_message = text
    if sedi_response is not None:
        row.sedi_response = sedi_response.strip()[:MAX_TURN_TEXT] or None
    try:
        prov = json.loads(row.provenance_json or "{}")
        if not isinstance(prov, dict):
            prov = {}
    except (TypeError, ValueError):
        prov = {}
    prov["user_edited_at"] = datetime.now(timezone.utc).isoformat()
    row.provenance_json = json.dumps(prov, ensure_ascii=False, separators=(",", ":"))
    db.commit()
    db.refresh(row)
    refresh_day_summary(db, user_id, _utc(row.created_at))
    zone, _ = _zone(db, user_id)
    return _turn_dict(row, zone)


def refresh_day_summary(db: Session, user_id: int, when_utc: Optional[datetime]) -> bool:
    """After a turn edit/delete: re-derive THAT day's DAILY summary if one already exists (never creates one, never
    touches other days, higher periods or the lifelong profile). Fail-open."""
    if when_utc is None:
        return False
    try:
        zone, _ = _zone(db, user_id)
        day = _local_day(when_utc, zone)
        if _daily_summary_of_day(db, user_id, day, zone) is None:
            return False
        from backend.app.services.i7.period_summaries import rebuild_summary

        noon = zone.localize(datetime.combine(day, time(12, 0))).astimezone(timezone.utc)
        rebuild_summary(db, user_id, "DAILY", now=noon, commit=True)
        return True
    except Exception:
        db.rollback()
        return False


# ----------------------------------------------------------------------------------------------------------------------
# the day read model
# ----------------------------------------------------------------------------------------------------------------------
def _daily_summary_of_day(db: Session, user_id: int, day: date, zone) -> Optional[models.UserPeriodSummary]:
    start, end = day_bounds_utc(day, zone)
    return (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.status == "active",
            models.UserPeriodSummary.period_start >= start - timedelta(hours=2),
            models.UserPeriodSummary.period_start < start + timedelta(hours=2),
        )
        .order_by(models.UserPeriodSummary.version.desc())
        .first()
    )


def _humanize(key: str) -> str:
    return " ".join(str(key).replace("_", " ").replace("-", " ").split())


def _summary_text(lang: str, signals: dict, turn_count: int) -> str:
    """One short deterministic sentence per fact Sedi derived that day. No raw text, no invention."""
    parts: list[str] = []
    topics = [_humanize(t) for t in (signals.get("topics") or [])][:3]
    done = signals.get("user_done") or {}
    done_total = sum(int(v or 0) for k, v in done.items() if k != "total") if isinstance(done, dict) else 0
    if isinstance(done, dict) and done.get("total"):
        done_total = int(done["total"])
    wb = signals.get("wellbeing") or {}
    wb_keys = [k for k in ("low_mood", "stress", "fatigue", "sleep_issue", "pain", "positive") if wb.get(k)]
    labels = {
        "fa": {
            "topics": "درباره‌ی {x} حرف زدیم.",
            "done": "{n} کار انجام دادی.",
            "wb": {
                "low_mood": "حالت چندان خوب نبود", "stress": "کمی استرس داشتی", "fatigue": "خسته بودی",
                "sleep_issue": "خوابت مشکل داشت", "pain": "درد داشتی", "positive": "حالت خوب بود",
            },
            "wb_join": "گفتی: {x}.",
            "turns": "{n} گفتگو داشتیم.",
        },
        "en": {
            "topics": "We talked about {x}.",
            "done": "You completed {n} things.",
            "wb": {
                "low_mood": "you felt low", "stress": "you felt stressed", "fatigue": "you were tired",
                "sleep_issue": "you had trouble sleeping", "pain": "you were in pain", "positive": "you felt good",
            },
            "wb_join": "You mentioned {x}.",
            "turns": "We had {n} conversations.",
        },
        "ar": {
            "topics": "تحدثنا عن {x}.",
            "done": "أنجزت {n} مهام.",
            "wb": {
                "low_mood": "كان مزاجك سيئًا", "stress": "كنت متوترًا", "fatigue": "كنت متعبًا",
                "sleep_issue": "واجهت صعوبة في النوم", "pain": "كان لديك ألم", "positive": "كان مزاجك جيدًا",
            },
            "wb_join": "ذكرت: {x}.",
            "turns": "أجرينا {n} محادثات.",
        },
    }[lang if lang in ("fa", "en", "ar") else "en"]
    sep = "، " if lang in ("fa", "ar") else ", "
    if topics:
        parts.append(labels["topics"].format(x=sep.join(topics)))
    if wb_keys:
        parts.append(labels["wb_join"].format(x=sep.join(labels["wb"][k] for k in wb_keys[:3])))
    if done_total:
        parts.append(labels["done"].format(n=done_total))
    hr_avg = int((signals.get("hr") or {}).get("avg", 0) or 0)
    if hr_avg:
        parts.append(
            {
                "fa": f"ضربان قلبت به‌طور میانگین حدود {hr_avg} بود.",
                "ar": f"كان متوسط نبض قلبك نحو {hr_avg}.",
                "en": f"Your heart rate averaged about {hr_avg}.",
            }[lang if lang in ("fa", "ar", "en") else "en"]
        )
    if not parts and turn_count:
        parts.append(labels["turns"].format(n=turn_count))
    return " ".join(parts)


def _chips(signals: dict) -> dict[str, Any]:
    plan = signals.get("plan") or {}
    done = signals.get("user_done") or {}
    return {
        "topics": [_humanize(t) for t in (signals.get("topics") or [])][:5],
        "wellbeing": [k for k in ("low_mood", "stress", "fatigue", "sleep_issue", "pain", "positive") if (signals.get("wellbeing") or {}).get(k)],
        "plan_done": int(plan.get("done", 0) or 0),
        "plan_total": int(plan.get("total", 0) or 0),
        "user_done": int(done.get("total", 0) or 0) if isinstance(done, dict) else 0,
        "hr_avg": int((signals.get("hr") or {}).get("avg", 0) or 0),
    }


def _event_dict(row: models.UserEvent) -> dict[str, Any]:
    from backend.app.services.i7.life_events import is_life_event, parse_life_meta

    life = is_life_event(row)
    meta = parse_life_meta(row.description) if life else None
    return {
        "id": int(row.id),
        "title": row.title,
        "kind": (meta or {}).get("kind") if life else row.event_type,
        "life_event": life,
        "status": row.status,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
    }


def _events_between(db: Session, user_id: int, start_utc: datetime, end_utc: datetime) -> list[models.UserEvent]:
    return (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.user_id == user_id,
            models.UserEvent.status != "cancelled",
            models.UserEvent.event_type != NOTE_EVENT_TYPE,
            models.UserEvent.starts_at >= _naive_utc(start_utc),
            models.UserEvent.starts_at < _naive_utc(end_utc),
        )
        .order_by(models.UserEvent.starts_at.asc())
        .limit(100)
        .all()
    )


def _notes_between(db: Session, user_id: int, start_utc: datetime, end_utc: datetime) -> list[models.UserEvent]:
    return (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.user_id == user_id,
            models.UserEvent.status == "completed",
            models.UserEvent.event_type == NOTE_EVENT_TYPE,
            models.UserEvent.starts_at >= _naive_utc(start_utc),
            models.UserEvent.starts_at < _naive_utc(end_utc),
        )
        .order_by(models.UserEvent.created_at.asc())
        .limit(100)
        .all()
    )


def _facts_of_day(db: Session, user_id: int, start_utc: datetime, end_utc: datetime) -> list[dict[str, Any]]:
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty
    from backend.app.services.memory.memory_contract import MemoryContract, render_stated_value

    out = []
    for r in list_facts_readonly_or_empty(db, user_id):
        when = _utc(getattr(r, "updated_at", None) or getattr(r, "created_at", None))
        if when is None or not (start_utc <= when < end_utc):
            continue
        permitted, _ = MemoryContract.i6_write_permitted(r.domain, r.key)
        out.append({"id": int(r.id), "value": render_stated_value(r.value_json), "editable": bool(permitted)})
    return out


def get_day(db: Session, user_id: int, day: date, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Everything Sedi remembers about one local day. Raw chat text only inside the 30-day window."""
    from backend.app.services.i6.consent_service import PERM_READ

    zone, tz_name = _zone(db, user_id)
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date()
    out: dict[str, Any] = {
        "date": day.isoformat(),
        "timezone": tz_name,
        "days_ago": (today - day).days,
        "raw_visible": raw_visible_for_day(day, zone, now=now),
        "consent": False,
        "turns": [],
        "summary": {"text": "", "chips": _chips({}), "derived": False},
        "events": [],
        "notes": [],
        "facts": [],
    }
    if not _has(db, user_id, PERM_READ):
        return out
    out["consent"] = True
    lang = _lang(db, user_id)
    start, end = day_bounds_utc(day, zone)
    turns: list[models.Memory] = []
    try:
        if out["raw_visible"]:
            turns = _eligible_turns_of_day(db, user_id, day, zone)
            out["turns"] = [_turn_dict(m, zone) for m in turns]
    except Exception:
        out["turns"] = []
    signals: dict = {}
    turn_count = len(turns)
    try:
        stored = _daily_summary_of_day(db, user_id, day, zone)
        if stored is not None:
            from backend.app.services.i7.derived_signals import signals_of

            signals = signals_of(stored)
            payload = json.loads(stored.structured_summary_json or "{}")
            turn_count = turn_count or int(payload.get("turn_count", 0) or 0)
            out["summary"]["derived"] = True
        else:  # no stored summary yet: derive the day's signals live (chat-less days still have gadget data)
            from backend.app.services.i7.derived_signals import collect_daily_signals

            signals = collect_daily_signals(db, user_id, day, turns)
    except Exception:
        signals = {}
    out["summary"]["text"] = _summary_text(lang, signals, turn_count)
    out["summary"]["chips"] = _chips(signals)
    try:
        out["events"] = [_event_dict(r) for r in _events_between(db, user_id, start, end)]
        out["notes"] = [_note_dict(r) for r in _notes_between(db, user_id, start, end)]
        out["facts"] = _facts_of_day(db, user_id, start, end)
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------------------------------------------------
# calendar
# ----------------------------------------------------------------------------------------------------------------------
def get_calendar(db: Session, user_id: int, start_day: date, end_day: date) -> dict[str, Any]:
    """Which local days in [start_day, end_day] hold a memory. Counts only — no text."""
    from backend.app.services.i6.consent_service import PERM_READ

    zone, tz_name = _zone(db, user_id)
    out: dict[str, Any] = {"from": start_day.isoformat(), "to": end_day.isoformat(), "timezone": tz_name, "consent": False, "days": []}
    if end_day < start_day or (end_day - start_day).days > MAX_CALENDAR_SPAN_DAYS or not _has(db, user_id, PERM_READ):
        return out
    out["consent"] = True
    start, _ = day_bounds_utc(start_day, zone)
    _, end = day_bounds_utc(end_day, zone)
    counts: dict[str, dict[str, int]] = {}

    def bump(d: Optional[date], key: str, n: int = 1) -> None:
        if d is None or not (start_day <= d <= end_day):
            return
        counts.setdefault(d.isoformat(), {"turns": 0, "events": 0, "notes": 0, "summary": 0})[key] += n

    try:
        for m in query_eligible_raw(db, user_id, limit=_SCAN_CAP * 2):
            bump(_local_day(m.created_at, zone), "turns")
    except Exception:
        pass
    try:
        for r in _events_between(db, user_id, start, end):
            bump(_local_day(r.starts_at, zone), "events")
        for r in _notes_between(db, user_id, start, end):
            bump(_local_day(r.starts_at, zone), "notes")
    except Exception:
        pass
    try:
        rows = (
            db.query(models.UserPeriodSummary)
            .filter(
                models.UserPeriodSummary.user_id == user_id,
                models.UserPeriodSummary.summary_type == "DAILY",
                models.UserPeriodSummary.status == "active",
                models.UserPeriodSummary.period_start >= start - timedelta(hours=2),
                models.UserPeriodSummary.period_start < end + timedelta(hours=2),
            )
            .all()
        )
        for r in rows:
            payload = json.loads(r.structured_summary_json or "{}")
            if int(payload.get("turn_count", 0) or 0) or payload.get("signals"):
                bump(_local_day(r.period_start + timedelta(hours=2), zone), "summary")
    except Exception:
        pass
    out["days"] = [{"date": k, **v} for k, v in sorted(counts.items())]
    return out


# ----------------------------------------------------------------------------------------------------------------------
# search
# ----------------------------------------------------------------------------------------------------------------------
def _snippet(text: str, needle: str, width: int = 60) -> str:
    flat = " ".join((text or "").split())
    i = norm(flat).find(needle)
    if i < 0:
        return flat[: width * 2]
    lo, hi = max(0, i - width), min(len(flat), i + len(needle) + width)
    return ("…" if lo else "") + flat[lo:hi] + ("…" if hi < len(flat) else "")


def search(
    db: Session,
    user_id: int,
    query: str,
    *,
    from_day: Optional[date] = None,
    to_day: Optional[date] = None,
    limit: int = MAX_SEARCH_RESULTS,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Keyword search. Raw chat text only inside the 30-day window; older days are searched through derived summaries,
    events, day notes and facts — never raw chat."""
    from backend.app.services.i6.consent_service import PERM_READ

    needle = norm(query)
    out: dict[str, Any] = {"query": query, "consent": False, "results": []}
    if len(needle) < 2 or not _has(db, user_id, PERM_READ):
        return out
    out["consent"] = True
    zone, _ = _zone(db, user_id)
    results: list[dict[str, Any]] = []

    def in_range(d: Optional[date]) -> bool:
        return d is not None and (from_day is None or d >= from_day) and (to_day is None or d <= to_day)

    def add(kind: str, d: Optional[date], text: str, ref_id: Optional[int] = None) -> None:
        if in_range(d):
            results.append({"type": kind, "date": d.isoformat(), "snippet": _snippet(text, needle), "id": ref_id})

    try:
        for m in query_eligible_raw(db, user_id, limit=_SCAN_CAP):
            blob = f"{m.user_message or ''} {m.sedi_response or ''}"
            if needle in norm(blob):
                add("chat", _local_day(m.created_at, zone), m.user_message if needle in norm(m.user_message) else blob, int(m.id))
    except Exception:
        pass
    try:
        rows = (
            db.query(models.UserEvent)
            .filter(models.UserEvent.user_id == user_id, models.UserEvent.status != "cancelled")
            .order_by(models.UserEvent.starts_at.desc())
            .limit(_SCAN_CAP)
            .all()
        )
        for r in rows:
            if needle in norm(f"{r.title or ''} {r.notes or ''}"):
                add("note" if r.event_type == NOTE_EVENT_TYPE else "event", _local_day(r.starts_at, zone), r.title or "", int(r.id))
    except Exception:
        pass
    try:
        from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty
        from backend.app.services.memory.memory_contract import render_stated_value

        for f in list_facts_readonly_or_empty(db, user_id):
            value = str(render_stated_value(f.value_json) or "")
            if needle in norm(value):
                add("fact", _local_day(getattr(f, "updated_at", None) or getattr(f, "created_at", None), zone), value, int(f.id))
    except Exception:
        pass
    try:
        rows = (
            db.query(models.UserPeriodSummary)
            .filter(
                models.UserPeriodSummary.user_id == user_id,
                models.UserPeriodSummary.summary_type == "DAILY",
                models.UserPeriodSummary.status == "active",
            )
            .order_by(models.UserPeriodSummary.period_start.desc())
            .limit(_SCAN_CAP)
            .all()
        )
        from backend.app.services.i7.derived_signals import signals_of

        for r in rows:
            topics = " ".join(_humanize(t) for t in (signals_of(r).get("topics") or []))
            if topics and needle in norm(topics):
                add("summary", _local_day(r.period_start + timedelta(hours=2), zone), topics)
    except Exception:
        pass
    results.sort(key=lambda r: r["date"], reverse=True)
    out["results"] = results[: max(1, min(int(limit), MAX_SEARCH_RESULTS))]
    out["total"] = len(results)
    return out
