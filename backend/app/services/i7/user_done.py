# backend.app.services.i7.user_done
"""R-031 - what the USER did is memory (2026-10-27).

When the user marks something done in My Schedule (took the medication, attended the appointment / meeting) it is
recorded ONCE through its owner (medication dose occurrence / UserEvent) and ONCE in the I10 interaction ledger, here.
Everything else READS this ledger - no copies:

- I7 daily signals (``user_done`` counts per domain) -> weekly / monthly / yearly merge, timeline-style memory;
- I10 reminders: a repeating event's occurrence that is done is not reminded again;
- chat context: Sedi may say "you took your morning medication today" (consent-gated by the caller);
- notification wording, profile summary, lifestyle hub (read the same signals).

Ledger row: ``interaction_events`` with ``source='schedule'``, ``event_type`` = DONE / UNDONE, ``source_id`` = the
occurrence id (``kind:ref:YYYYMMDD[:HHMM]``). An occurrence is "done" while its LATEST row is DONE (undo = a newer
UNDONE row), so the user can always take it back. No schema change. Only counts, domains and ids - never titles or
health detail.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from backend.app import models

DONE_EVENT = "user_schedule_done"
UNDONE_EVENT = "user_schedule_undone"
LEDGER_SOURCE = "schedule"

DOMAINS = ("medication", "appointment", "meeting", "other")
KINDS = ("event", "medication")

_APPOINTMENT_TYPES = frozenset(
    {
        "doctor_visit",
        "lab_test",
        "imaging",
        "surgery",
        "physiotherapy",
        "nursing_visit",
        "care_followup",
        "medication_review",
    }
)
_MEETING_TYPES = frozenset({"work_meeting", "exam", "deadline"})


def domain_for(kind: str, event_type: Optional[str] = None, event_domain: Optional[str] = None) -> str:
    """Coarse, non-revealing domain of a done item (the only thing that reaches memory)."""
    if kind == "medication":
        return "medication"
    if event_type in _APPOINTMENT_TYPES or event_domain in ("medical", "care"):
        return "appointment"
    if event_type in _MEETING_TYPES or event_domain in ("work", "education"):
        return "meeting"
    return "other"


def occurrence_id(kind: str, ref_id: int, day: date, hhmm: Optional[str] = None) -> str:
    base = f"{kind}:{int(ref_id)}:{day.strftime('%Y%m%d')}"
    if hhmm:
        base += ":" + hhmm.replace(":", "")
    return base


def record(
    db: Session,
    user_id: int,
    *,
    kind: str,
    ref_id: int,
    day: date,
    hhmm: Optional[str],
    domain: str,
    done: bool,
) -> models.InteractionEvent:
    """Append one DONE / UNDONE ledger row for the occurrence (idempotent per state: no duplicate of the latest state)."""
    from backend.app.services.gate4.interaction_event_service import create_interaction_event

    occ = occurrence_id(kind, ref_id, day, hhmm)
    if is_done(db, user_id, occ) == done:
        latest = _latest_row(db, user_id, occ)
        if latest is not None:
            return latest
    return create_interaction_event(
        db,
        user_id=user_id,
        event_type=DONE_EVENT if done else UNDONE_EVENT,
        source=LEDGER_SOURCE,
        source_type=f"schedule_{kind}",
        source_id=occ,
        metadata={
            "domain": domain,
            "kind": kind,
            "ref_id": int(ref_id),
            "day": day.isoformat(),
            "time": hhmm,
        },
    )


def _latest_row(db: Session, user_id: int, occ: str) -> Optional[models.InteractionEvent]:
    return (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.user_id == user_id,
            models.InteractionEvent.source == LEDGER_SOURCE,
            models.InteractionEvent.source_id == occ,
            models.InteractionEvent.event_type.in_((DONE_EVENT, UNDONE_EVENT)),
        )
        .order_by(models.InteractionEvent.id.desc())
        .first()
    )


def is_done(db: Session, user_id: int, occ: str) -> bool:
    row = _latest_row(db, user_id, occ)
    return row is not None and row.event_type == DONE_EVENT


def is_event_occurrence_done(db: Session, user_id: int, event_id: int, day: date) -> bool:
    """Used by the reminder scheduler: a repeating occurrence the user already did is not reminded again."""
    return is_done(db, user_id, occurrence_id("event", event_id, day))


def _meta(row: models.InteractionEvent) -> Dict[str, Any]:
    try:
        data = json.loads(row.metadata_json or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def done_occurrences(db: Session, user_id: int, day: date) -> List[Dict[str, Any]]:
    """Occurrences of ``day`` whose latest state is DONE: [{id, kind, ref_id, domain, time, done_at}]."""
    prefix_day = day.strftime("%Y%m%d")
    rows = (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.user_id == user_id,
            models.InteractionEvent.source == LEDGER_SOURCE,
            models.InteractionEvent.event_type.in_((DONE_EVENT, UNDONE_EVENT)),
            models.InteractionEvent.source_id.like(f"%:{prefix_day}%"),
        )
        .order_by(models.InteractionEvent.id.asc())
        .all()
    )
    latest: Dict[str, models.InteractionEvent] = {}
    for r in rows:
        latest[str(r.source_id)] = r
    out: List[Dict[str, Any]] = []
    for occ, r in latest.items():
        if r.event_type != DONE_EVENT:
            continue
        m = _meta(r)
        if m.get("day") != day.isoformat():
            continue
        out.append(
            {
                "id": occ,
                "kind": m.get("kind"),
                "ref_id": m.get("ref_id"),
                "domain": m.get("domain") or "other",
                "time": m.get("time"),
                "done_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return out


def done_counts_for_day(db: Session, user_id: int, day: date) -> Dict[str, int]:
    """I7 daily signal: {domain: count} of things the user did that day (empty when none)."""
    counts: Counter = Counter()
    for item in done_occurrences(db, user_id, day):
        dom = item["domain"] if item["domain"] in DOMAINS else "other"
        counts[dom] += 1
    return dict(counts)


def merge_done_counts(parts: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    total: Counter = Counter()
    for p in parts:
        for k, v in (p or {}).items():
            total[str(k)] += int(v or 0)
    return {k: v for k, v in total.items() if v}


def done_today_hint(db: Session, user_id: int, language: Optional[str], today: date) -> str:
    """One bounded line for Sedi's chat context ('' when nothing). Domains only, never titles."""
    counts = done_counts_for_day(db, user_id, today)
    if not counts:
        return ""
    lang = (language or "fa").strip().lower().split("-")[0]
    names = {
        "fa": {"medication": "دارو", "appointment": "نوبت/مراجعه", "meeting": "جلسه/کار", "other": "یک کار دیگر"},
        "ar": {"medication": "الدواء", "appointment": "الموعد", "meeting": "الاجتماع/العمل", "other": "عمل آخر"},
        "en": {"medication": "medication", "appointment": "an appointment", "meeting": "a meeting/work item", "other": "another item"},
    }
    table = names.get(lang, names["en"])
    items = ", ".join(table[d] for d in DOMAINS if counts.get(d))
    if lang == "fa":
        return (
            f"[کارهای_انجام‌شده_امروز] کاربر امروز خودش این‌ها را انجام‌شده علامت زده: {items}. "
            "اگر طبیعی بود، با یک جمله‌ی گرم قدردانی کن؛ جزئیات از خودت اضافه نکن و دوباره یادآوری‌شان نکن."
        )
    if lang == "ar":
        return (
            f"[أعمال_أنجزها_اليوم] علّم المستخدم اليوم أنه أنجز: {items}. "
            "إن كان مناسباً فاشكريه بجملة دافئة؛ لا تضيفي تفاصيل ولا تذكّريه بها مجدداً."
        )
    return (
        f"[DONE_TODAY] The user marked these as done today: {items}. "
        "If it fits, thank them warmly in one sentence; add no details and do not remind them of these again."
    )
